#!/usr/bin/env python3
"""Repair only the traced context-length shape constants in pinned VoxLock ONNX.

Requires ONNX; does not download, retrain, quantize or optimize any model.
Derived graph is experimental. This correction provides no quality guarantee.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re

import onnx
from onnx import helper, numpy_helper, TensorProto


SOURCE_SHA256 = "7b57c1bfd5acd5b33768a9dff09d9af487d45374b3ba0b991e541ff121eaa337"
PATTERN = re.compile(r"^/attenFuse/multihead_attn(?:_([1-9]|[12][0-9]|3[01]))?/Constant_(30|31)$")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def records(items):
    return [(item.name, digest(item.SerializeToString())) for item in items]


def collection_digest(rows):
    return digest(json.dumps(rows, separators=(",", ":")).encode())


def repair(source, destination):
    if source.resolve() == destination.resolve():
        raise ValueError("Derived output must not overwrite the pinned input")
    if digest(source.read_bytes()) != SOURCE_SHA256:
        raise ValueError("Input is not the pinned int8-full VoxLock graph")
    model = onnx.load(str(source), load_external_data=False)
    onnx.checker.check_model(model, full_check=True)
    if any(value.external_data for value in model.graph.initializer):
        raise ValueError("External tensor data is outside this audited transformation")
    old_initializer_records = records(model.graph.initializer)
    old_nodes = list(model.graph.node)
    old_node_records = records(old_nodes)
    by_name = {node.name: node for node in old_nodes}
    if len(by_name) != len(old_nodes):
        raise ValueError("Expected unique original node names")
    consumers = {}
    for node in old_nodes:
        for value in node.input:
            consumers.setdefault(value, []).append(node)
    context = next(value for value in model.graph.input if value.name == "context")
    dimensions = context.type.tensor_type.shape.dim
    if (len(dimensions) != 3 or dimensions[0].dim_value != 1 or
            dimensions[1].dim_value != 512 or dimensions[2].dim_param != "Fc"):
        raise ValueError("Unexpected context contract")
    expected_names = {f"/attenFuse/multihead_attn{suffix}/Constant_{number}"
                      for suffix in [""] + [f"_{index}" for index in range(1, 32)]
                      for number in (30, 31)}
    selected = {node.name for node in old_nodes if PATTERN.fullmatch(node.name)}
    if selected != expected_names:
        raise ValueError("Expected exactly 64 audited shape-constant nodes")
    # Guard against another unaccounted traced 298 value in Constant tensors.
    containing_298 = set()
    for node in old_nodes:
        if node.op_type == "Constant":
            for attribute in node.attribute:
                if attribute.type == onnx.AttributeProto.TENSOR:
                    if (numpy_helper.to_array(attribute.t) == 298).any():
                        containing_298.add(node.name)
    if containing_298 != selected:
        raise ValueError("Unexpected extra or missing 298 constants")
    changed = []
    for name in sorted(selected):
        node = by_name[name]
        match = PATTERN.fullmatch(name)
        number = int(match.group(2))
        prefix = name.rsplit("/", 1)[0]
        if (node.op_type != "Constant" or len(node.input) or len(node.output) != 1 or
                len(node.attribute) != 1 or node.attribute[0].name != "value"):
            raise ValueError(f"Unexpected constant structure: {name}")
        tensor = node.attribute[0].t
        values = numpy_helper.to_array(tensor)
        if tensor.data_type != TensorProto.INT64 or list(values.shape) != [1] or values.tolist() != [298]:
            raise ValueError(f"Unexpected shape value: {name}")
        concat_number, reshape_number = ((3, 4) if number == 30 else (4, 5))
        concat = by_name[f"{prefix}/Concat_{concat_number}"]
        reshape = by_name[f"{prefix}/Reshape_{reshape_number}"]
        if (consumers.get(node.output[0]) != [concat] or concat.op_type != "Concat" or
                len(concat.input) != 3 or concat.input[0] != node.output[0] or
                len(concat.output) != 1 or len(concat.attribute) != 1 or
                concat.attribute[0].name != "axis" or concat.attribute[0].i != 0 or
                consumers.get(concat.output[0]) != [reshape] or reshape.op_type != "Reshape" or
                len(reshape.input) != 2 or reshape.input[1] != concat.output[0]):
            raise ValueError(f"Unexpected sole shape consumer: {name}")
        changed.append({"node": name, "concat": concat.name, "reshape": reshape.name})
    shape, index, length = [f"danygramm_dynamic_context_{suffix}" for suffix in ("shape", "index", "length")]
    known_values = {name for node in old_nodes for name in (*node.input, *node.output)}
    if known_values.intersection((shape, index, length)):
        raise ValueError("Inserted value names collide with the original graph")
    added = [helper.make_node("Shape", ["context"], [shape], name=shape),
             helper.make_node("Constant", [], [index], name=index,
                              value=helper.make_tensor(index, TensorProto.INT64, [1], [2])),
             helper.make_node("Gather", [shape, index], [length], name=length, axis=0)]
    # Keep every downstream node byte-identical: each replaced Constant keeps
    # its old output name as an Identity alias of the common runtime length.
    replacement = [helper.make_node("Identity", [length], list(node.output), name=node.name)
                   if node.name in selected else node for node in old_nodes]
    del model.graph.node[:]
    model.graph.node.extend(added + replacement)
    onnx.checker.check_model(model, full_check=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(destination))
    saved = onnx.load(str(destination), load_external_data=False)
    onnx.checker.check_model(saved, full_check=True)
    new_initializer_records = records(saved.graph.initializer)
    if old_initializer_records != new_initializer_records:
        raise ValueError("An original initializer changed")
    unchanged_before = [(name, value) for name, value in old_node_records if name not in selected]
    unchanged_after = records(node for node in saved.graph.node if node.name in by_name and node.name not in selected)
    if unchanged_before != unchanged_after:
        raise ValueError("An unrelated original node changed")
    if len(saved.graph.node) != len(old_nodes) + 3 or len(changed) != 64:
        raise ValueError("Unexpected graph size after repair")
    if digest(source.read_bytes()) != SOURCE_SHA256:
        raise ValueError("Pinned input changed during the transformation")
    return {"purpose": "Experimental context-length export repair; no quality or product claim",
            "source": str(source.resolve()), "source_sha256": SOURCE_SHA256,
            "derived": str(destination.resolve()), "derived_sha256": digest(destination.read_bytes()),
            "derived_bytes": destination.stat().st_size, "onnx_version": onnx.__version__,
            "checker_full_check": True, "original_node_count": len(old_nodes),
            "derived_node_count": len(saved.graph.node), "replaced_constants": changed,
            "inserted_shape_nodes": [node.name for node in added],
            "unchanged_initializer_count": len(old_initializer_records),
            "unchanged_initializer_collection_sha256": collection_digest(old_initializer_records),
            "unchanged_other_node_count": len(unchanged_before),
            "unchanged_other_node_collection_sha256": collection_digest(unchanged_before),
            "all_original_initializers_unchanged": True, "all_other_original_nodes_unchanged": True,
            "ir_version": saved.ir_version, "opsets": [(op.domain, op.version) for op in saved.opset_import]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if len({path.resolve() for path in (args.input, args.output, args.manifest)}) != 3:
        parser.error("Input, derived output and audit manifest must be distinct paths")
    report = repair(args.input, args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("derived", "derived_sha256", "checker_full_check",
                     "unchanged_initializer_count", "unchanged_other_node_count")}, indent=2))


if __name__ == "__main__":
    main()
