import { useEffect, useState } from "react";
import type { CircuitData, NeuronDetail, Partner } from "../api";
import { api } from "../api";
import { roleColor } from "../colors";
import { signLabel } from "../format";

interface NeuronPanelProps {
  circuit: string;
  data: CircuitData;
  selected: number | null;
  ablated: Set<number>;
  onSelect: (index: number) => void;
  onToggleAblate: (index: number) => void;
}

/**
 * Synapse sign = sign of the PRESYNAPTIC neuron (Dale's law). For inputs that is the
 * partner's sign; for outputs it is the selected neuron's own sign (`outgoingSign`).
 */
function PartnerTable(props: {
  title: string;
  partners: Partner[];
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
    <div className="partner-table">
      <h4>{props.title}</h4>
      <table>
        <thead>
          <tr>
            <th>type</th>
            <th>bodyId</th>
            <th className="num">synapses</th>
            <th>synapse sign</th>
          </tr>
        </thead>
        <tbody>
          {props.partners.map((p) => (
            <tr key={p.index} className="clickable" onClick={() => props.onSelect(p.index)}>
              <td>{p.type}</td>
              <td className="mono">{p.body_id}</td>
              <td className="num">{p.synapses}</td>
              <td className={`sign sign-${synapseSign(p)}`}>{signLabel(synapseSign(p))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Details of the clicked neuron: identity, NT/sign provenance, degrees, top partners. */
export default function NeuronPanel(props: NeuronPanelProps) {
  const [detail, setDetail] = useState<NeuronDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (props.selected === null) {
      return;
    }
    const bodyId = props.data.body_ids[props.selected];
    let cancelled = false;
    api
      .neuron(props.circuit, bodyId)
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
      <PartnerTable title="Top inputs" partners={detail.top_inputs} onSelect={props.onSelect} />
      <PartnerTable
        title="Top outputs"
        partners={detail.top_outputs}
        onSelect={props.onSelect}
        outgoingSign={detail.sign}
      />
    </div>
  );
}
