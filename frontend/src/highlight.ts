import type { CircuitData, PathLevel, PathOut } from "./api";
import type { Highlight } from "./GraphView";

/** Convert a found path into graph nodes/edges to highlight. */
export function pathHighlight(data: CircuitData, path: PathOut, level: PathLevel): Highlight {
  const nodes = new Set<number>();
  const edges: Array<[number, number]> = [];
  if (level === "neuron") {
    for (const node of path.nodes) {
      nodes.add(node.index);
    }
    for (let i = 0; i + 1 < path.nodes.length; i += 1) {
      edges.push([path.nodes[i].index, path.nodes[i + 1].index]);
    }
    return { nodes, edges };
  }
  const typeSets: Set<number>[] = path.nodes.map(() => new Set<number>());
  const position = new Map<string, number[]>();
  path.nodes.forEach((node, i) => {
    const list = position.get(node.type);
    if (list === undefined) {
      position.set(node.type, [i]);
    } else {
      list.push(i);
    }
  });
  for (let n = 0; n < data.types.length; n += 1) {
    const steps = position.get(data.types[n]);
    if (steps !== undefined) {
      nodes.add(n);
      for (const step of steps) {
        typeSets[step].add(n);
      }
    }
  }
  for (let e = 0; e < data.edge_pre.length; e += 1) {
    const pre = data.edge_pre[e];
    const post = data.edge_post[e];
    for (let i = 0; i + 1 < typeSets.length; i += 1) {
      if (typeSets[i].has(pre) && typeSets[i + 1].has(post)) {
        edges.push([pre, post]);
      }
    }
  }
  return { nodes, edges };
}
