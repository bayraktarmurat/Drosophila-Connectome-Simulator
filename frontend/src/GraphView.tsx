import Graph from "graphology";
import { useEffect, useLayoutEffect, useRef } from "react";
import Sigma from "sigma";
import type { EdgeDisplayData, NodeDisplayData } from "sigma/types";
import type { CircuitData } from "./api";
import { ABLATED, DIMMED, EDGE_ELECTRICAL, GLOW, HIGHLIGHT, edgeColor, roleColor, typeColor } from "./colors";

export interface Highlight {
  nodes: Set<number>;
  edges: Array<[number, number]>;
}

export type ColorBy = "role" | "type";

interface GraphViewProps {
  data: CircuitData;
  colorBy: ColorBy;
  minEdgeWeight: number;
  showExtraEdges: boolean;
  selected: number | null;
  highlight: Highlight | null;
  ablated: Set<number>;
  activity: Map<number, number> | null;
  onNodeClick: (index: number) => void;
  onStageClick: () => void;
}

const ROLE_SIZE: Record<string, number> = {
  input: 2.5,
  interneuron: 1.8,
  hub: 9,
  output: 5,
};

const MAX_FORCED_LABELS = 25;

function edgeKey(pre: number, post: number): string {
  return `${pre}>${post}`;
}

function nodeSize(role: string): number {
  const size = ROLE_SIZE[role];
  if (size === undefined) {
    return 2;
  }
  return size;
}

function nodeLabel(data: CircuitData, index: number): string {
  const role = data.roles[index];
  const instance = data.instances[index];
  if ((role === "hub" || role === "output") && instance.length > 0) {
    return instance;
  }
  return data.types[index];
}

function buildGraph(
  data: CircuitData,
  colorBy: ColorBy,
  minEdgeWeight: number,
  showExtraEdges: boolean,
  highlight: Highlight | null,
): Graph {
  const graph = new Graph({ type: "directed", multi: true });
  for (let i = 0; i < data.body_ids.length; i += 1) {
    let color = roleColor(data.roles[i]);
    if (colorBy === "type") {
      color = typeColor(data.types[i]);
    }
    graph.addNode(String(i), {
      index: i,
      x: data.x[i],
      y: data.y[i],
      size: nodeSize(data.roles[i]),
      color,
      label: nodeLabel(data, i),
      role: data.roles[i],
    });
  }
  const forced = new Set<string>();
  if (highlight !== null) {
    for (const [pre, post] of highlight.edges) {
      forced.add(edgeKey(pre, post));
    }
  }
  for (let e = 0; e < data.edge_pre.length; e += 1) {
    const pre = data.edge_pre[e];
    const post = data.edge_post[e];
    const weight = data.edge_weight[e];
    const key = edgeKey(pre, post);
    if (weight < minEdgeWeight && !forced.has(key)) {
      continue;
    }
    graph.addDirectedEdgeWithKey(key, String(pre), String(post), {
      size: 0.3 + Math.log10(weight) * 0.6,
      color: edgeColor(data.signs[pre]),
      pre,
      post,
      electrical: false,
    });
  }
  if (showExtraEdges) {
    for (let e = 0; e < data.extra_edge_pre.length; e += 1) {
      const pre = data.extra_edge_pre[e];
      const post = data.extra_edge_post[e];
      graph.addDirectedEdgeWithKey(`gap:${edgeKey(pre, post)}`, String(pre), String(post), {
        size: 3,
        color: EDGE_ELECTRICAL,
        pre,
        post,
        electrical: true,
      });
    }
  }
  return graph;
}

export default function GraphView(props: GraphViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const stateRef = useRef(props);
  useLayoutEffect(() => {
    stateRef.current = props;
  });

  // Build (or rebuild) the graph when structure-affecting props change.
  useEffect(() => {
    const container = containerRef.current;
    if (container === null) {
      return;
    }
    const graph = buildGraph(
      props.data,
      props.colorBy,
      props.minEdgeWeight,
      props.showExtraEdges,
      props.highlight,
    );
    if (sigmaRef.current !== null) {
      sigmaRef.current.setGraph(graph);
      return;
    }
    const highlightEdgeKeys = () => {
      const keys = new Set<string>();
      const current = stateRef.current.highlight;
      if (current !== null) {
        for (const [pre, post] of current.edges) {
          keys.add(edgeKey(pre, post));
        }
      }
      return keys;
    };
    let cachedHighlight: Highlight | null = null;
    let cachedKeys = new Set<string>();

    const sigma = new Sigma(graph, container, {
      settings: {
        itemSizesReference: "screen",
        labelRenderedSizeThreshold: 7,
        labelDensity: 0.6,
        hideEdgesOnMove: true,
        minCameraRatio: 0.02,
        maxCameraRatio: 4,
      },
      nodeReducer: (_key, _data, attrs) => {
        const state = stateRef.current;
        const index = attrs.index as number;
        const result: Partial<NodeDisplayData> = {};
        if (state.highlight !== null) {
          if (state.highlight.nodes.has(index)) {
            result.zIndex = 2;
            result.size = Math.max(attrs.size as number, 5);
            const role = attrs.role as string;
            if (state.highlight.nodes.size <= MAX_FORCED_LABELS || role === "hub" || role === "output") {
              result.labelVisibility = "visible";
            }
          } else {
            result.color = DIMMED;
            result.labelVisibility = "hidden";
            result.zIndex = 0;
          }
        }
        if (state.ablated.has(index)) {
          result.color = ABLATED;
          result.label = `✕ ${attrs.label as string}`;
          result.zIndex = 3;
        }
        if (state.activity !== null) {
          const level = state.activity.get(index);
          if (level !== undefined && level > 0) {
            result.color = GLOW;
            result.size = (attrs.size as number) * (1 + 1.5 * level) + 1;
            result.zIndex = 4;
          }
        }
        if (state.selected === index) {
          result.highlighted = true;
          result.labelVisibility = "visible";
          result.zIndex = 5;
        }
        return result;
      },
      edgeReducer: (key, _data, attrs) => {
        const state = stateRef.current;
        const result: Partial<EdgeDisplayData> = {};
        if (state.ablated.has(attrs.pre as number)) {
          result.visibility = "hidden";
          return result;
        }
        if (state.highlight !== null) {
          if (state.highlight !== cachedHighlight) {
            cachedHighlight = state.highlight;
            cachedKeys = highlightEdgeKeys();
          }
          if (cachedKeys.has(key)) {
            result.color = HIGHLIGHT;
            result.size = 2.5;
            result.zIndex = 2;
          } else if (attrs.electrical !== true) {
            result.visibility = "hidden";
          }
        }
        return result;
      },
    });
    sigma.on("clickNode", ({ node }) => {
      stateRef.current.onNodeClick(Number(node));
    });
    sigma.on("clickStage", () => {
      stateRef.current.onStageClick();
    });
    sigmaRef.current = sigma;
  }, [props.data, props.colorBy, props.minEdgeWeight, props.showExtraEdges, props.highlight]);

  // Cheap visual updates: reducers read stateRef, so only a refresh is needed.
  useEffect(() => {
    if (sigmaRef.current !== null) {
      sigmaRef.current.refresh();
    }
  }, [props.selected, props.ablated, props.activity, props.highlight]);

  useEffect(() => {
    return () => {
      if (sigmaRef.current !== null) {
        sigmaRef.current.kill();
        sigmaRef.current = null;
      }
    };
  }, []);

  return <div className="graph-container" ref={containerRef} />;
}
