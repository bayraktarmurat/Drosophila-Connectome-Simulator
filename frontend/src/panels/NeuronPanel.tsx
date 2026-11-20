import { useEffect, useState } from "react";
import type { CircuitData, NeuronDetail, Partner } from "../api";
import { api } from "../api";
import { roleColor } from "../colors";
import Modal from "../components/Modal";
import { signLabel } from "../format";
import type { Highlight } from "../GraphView";

interface NeuronPanelProps {
  circuit: string;
  data: CircuitData;
  selected: number | null;
  ablated: Set<number>;
  onSelect: (index: number) => void;
  onToggleAblate: (index: number) => void;
  onHighlight: (value: Highlight | null) => void;
}

/** Rows shown in the side panel; the rest are in the "show all" window. */
const PANEL_ROWS = 12;

type Direction = "inputs" | "outputs";

/**
 * Synapse sign = sign of the PRESYNAPTIC neuron (Dale's law). For inputs that is the
 * partner's sign; for outputs it is the selected neuron's own sign (`outgoingSign`).
 */
function PartnerTable(props: {
  partners: Partner[];
  data: CircuitData;
  onSelect: (index: number) => void;
  outgoingSign?: number;
}) {
  const synapseSign = (partner: Partner) => {
    if (props.outgoingSign !== undefined) {
      return props.outgoingSign;
    }
    return partner.sign;
  };
  return (
    <table>
      <thead>
        <tr>
          <th>neuron</th>
          <th>bodyId</th>
          <th>NT</th>
          <th className="num">synapses</th>
          <th>synapse sign</th>
        </tr>
      </thead>
      <tbody>
        {props.partners.map((p) => {
          let name = p.type;
          if (p.instance.length > 0) {
            name = p.instance;
          }
          const sign = synapseSign(p);
          return (
            <tr key={p.index} className="clickable" onClick={() => props.onSelect(p.index)}>
              <td>
                <span className="role-dot" style={{ background: roleColor(props.data.roles[p.index]) }} />
                {name}
              </td>
              <td className="mono">{p.body_id}</td>
              <td className="muted">{props.data.nts[p.index]}</td>
              <td className="num">{p.synapses}</td>
              <td className={`sign sign-${sign}`}>{signLabel(sign)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function filterPartners(partners: Partner[], data: CircuitData, text: string): Partner[] {
  const query = text.trim().toLowerCase();
  if (query.length === 0) {
    return partners;
  }
  return partners.filter((p) => {
    const haystack = `${p.type} ${p.instance} ${p.body_id} ${data.nts[p.index]}`.toLowerCase();
    return haystack.includes(query);
  });
}

function partnerHighlight(center: number, partners: Partner[], direction: Direction): Highlight {
  const nodes = new Set<number>([center]);
  const edges: Array<[number, number]> = [];
  for (const p of partners) {
    nodes.add(p.index);
    if (direction === "inputs") {
      edges.push([p.index, center]);
    } else {
      edges.push([center, p.index]);
    }
  }
  return { nodes, edges };
}

/** Details of the clicked neuron: identity, NT/sign provenance, degrees, all partners. */
export default function NeuronPanel(props: NeuronPanelProps) {
  const [detail, setDetail] = useState<NeuronDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fullList, setFullList] = useState<Direction | null>(null);
  const [filterText, setFilterText] = useState("");

  useEffect(() => {
    if (props.selected === null) {
      return;
    }
    const bodyId = props.data.body_ids[props.selected];
    let cancelled = false;
    api
      .neuron(props.circuit, bodyId, 0)
      .then((value) => {
        if (!cancelled) {
          setDetail(value);
          setError(null);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [props.selected, props.circuit, props.data]);

  if (props.selected === null) {
    return <p className="hint">Click a neuron in the graph to inspect it.</p>;
  }
  if (error !== null) {
    return <p className="error">{error}</p>;
  }
  if (detail === null || detail.index !== props.selected) {
    return <p className="hint">Loading…</p>;
  }
  let ablateLabel = "Ablate this neuron";
  if (props.ablated.has(detail.index)) {
    ablateLabel = "Restore this neuron";
  }
  let signWarning = null;
  if (detail.sign_source === "default") {
    signWarning = <p className="warning">No usable NT prediction: sign is the config default.</p>;
  }

  const select = (index: number) => {
    setFullList(null);
    setFilterText("");
    props.onSelect(index);
  };

  const showAllButton = (direction: Direction, partners: Partner[]) => {
    if (partners.length <= PANEL_ROWS) {
      return null;
    }
    return (
      <button className="small" onClick={() => setFullList(direction)}>
        show all {partners.length}
      </button>
    );
  };

  const section = (direction: Direction, partners: Partner[], outgoingSign?: number) => {
    let title = `Inputs (${partners.length} presynaptic neurons)`;
    if (direction === "outputs") {
      title = `Outputs (${partners.length} postsynaptic neurons)`;
    }
    return (
      <div className="partner-table">
        <h4>
          {title}{" "}
          <button
            className="small"
            onClick={() => props.onHighlight(partnerHighlight(detail.index, partners, direction))}
          >
            show on graph
          </button>
          {showAllButton(direction, partners)}
        </h4>
        <PartnerTable
          partners={partners.slice(0, PANEL_ROWS)}
          data={props.data}
          onSelect={select}
          outgoingSign={outgoingSign}
        />
      </div>
    );
  };

  let modal = null;
  if (fullList !== null) {
    let partners = detail.top_inputs;
    let outgoingSign: number | undefined = undefined;
    let title = `All inputs of ${detail.instance} (${detail.body_id})`;
    if (fullList === "outputs") {
      partners = detail.top_outputs;
      outgoingSign = detail.sign;
      title = `All outputs of ${detail.instance} (${detail.body_id})`;
    }
    const shown = filterPartners(partners, props.data, filterText);
    modal = (
      <Modal title={title} onClose={() => setFullList(null)}>
        <div className="modal-tools">
          <input
            autoFocus
            placeholder="filter by type, instance, bodyId or NT"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
          />
          <span className="muted">
            {shown.length} / {partners.length}
          </span>
        </div>
        <PartnerTable partners={shown} data={props.data} onSelect={select} outgoingSign={outgoingSign} />
      </Modal>
    );
  }

  return (
    <div className="neuron-panel">
      <h3>
        <span className="role-dot" style={{ background: roleColor(detail.role) }} />
        {detail.type} <span className="muted mono">{detail.body_id}</span>
      </h3>
      <dl className="facts">
        <dt>instance</dt>
        <dd>{detail.instance}</dd>
        <dt>role</dt>
        <dd>{detail.role}</dd>
        <dt>soma side</dt>
        <dd>{detail.soma_side}</dd>
        <dt>neurotransmitter</dt>
        <dd>{detail.consensus_nt}</dd>
        <dt>model sign</dt>
        <dd>
          {signLabel(detail.sign)} <span className="muted">(from {detail.sign_source})</span>
        </dd>
        <dt>in circuit: in / out</dt>
        <dd>
          {detail.in_degree} partners, {detail.in_synapses} syn / {detail.out_degree} partners,{" "}
          {detail.out_synapses} syn
        </dd>
        <dt>whole dataset: post / pre</dt>
        <dd>
          {detail.total_post} / {detail.total_pre}
        </dd>
      </dl>
      {signWarning}
      <button onClick={() => props.onToggleAblate(detail.index)}>{ablateLabel}</button>
      {section("inputs", detail.top_inputs)}
      {section("outputs", detail.top_outputs, detail.sign)}
      {modal}
    </div>
  );
}
