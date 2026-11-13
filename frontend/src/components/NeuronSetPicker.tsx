import { useId, useState } from "react";
import type { CircuitData, NeuronSet } from "../api";
import { resolveSet } from "../api";

interface NeuronSetPickerProps {
  label: string;
  data: CircuitData;
  value: NeuronSet;
  onChange: (value: NeuronSet) => void;
  allowRoles?: boolean;
}

const ROLES = ["input", "hub", "output", "interneuron"];

/** Choose cell types (autocomplete), roles and individual bodyIds. */
export default function NeuronSetPicker(props: NeuronSetPickerProps) {
  const listId = useId();
  const [draft, setDraft] = useState("");
  const typeNames = props.data.type_summary.map((t) => t.type);
  const count = resolveSet(props.data, props.value).length;

  const addDraft = () => {
    const text = draft.trim();
    if (text.length === 0) {
      return;
    }
    const asNumber = Number(text);
    if (Number.isInteger(asNumber) && props.data.body_ids.includes(asNumber)) {
      if (!props.value.body_ids.includes(asNumber)) {
        props.onChange({ ...props.value, body_ids: [...props.value.body_ids, asNumber] });
      }
    } else if (typeNames.includes(text)) {
      if (!props.value.types.includes(text)) {
        props.onChange({ ...props.value, types: [...props.value.types, text] });
      }
    }
    setDraft("");
  };

  const removeType = (name: string) => {
    props.onChange({ ...props.value, types: props.value.types.filter((t) => t !== name) });
  };
  const removeBody = (id: number) => {
    props.onChange({ ...props.value, body_ids: props.value.body_ids.filter((b) => b !== id) });
  };
  const toggleRole = (role: string) => {
    if (props.value.roles.includes(role)) {
      props.onChange({ ...props.value, roles: props.value.roles.filter((r) => r !== role) });
    } else {
      props.onChange({ ...props.value, roles: [...props.value.roles, role] });
    }
  };

  let roleBoxes = null;
  if (props.allowRoles !== false) {
    roleBoxes = (
      <div className="roles">
        {ROLES.map((role) => (
          <label key={role} className="check">
            <input
              type="checkbox"
              checked={props.value.roles.includes(role)}
              onChange={() => toggleRole(role)}
            />
            {role}
          </label>
        ))}
      </div>
    );
  }

  return (
    <div className="picker">
      <div className="picker-head">
        <span className="field-label">{props.label}</span>
        <span className="muted">{count} neurons</span>
      </div>
      {roleBoxes}
      <div className="chips">
        {props.value.types.map((name) => (
          <span key={name} className="chip">
            {name}
            <button onClick={() => removeType(name)} aria-label={`remove ${name}`}>
              ×
            </button>
          </span>
        ))}
        {props.value.body_ids.map((id) => (
          <span key={id} className="chip chip-body">
            {id}
            <button onClick={() => removeBody(id)} aria-label={`remove ${id}`}>
              ×
            </button>
          </span>
        ))}
      </div>
      <div className="picker-input">
        <input
          list={listId}
          value={draft}
          placeholder="add cell type or bodyId"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              addDraft();
            }
          }}
        />
        <button onClick={addDraft}>Add</button>
        <datalist id={listId}>
          {typeNames.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </div>
    </div>
  );
}
