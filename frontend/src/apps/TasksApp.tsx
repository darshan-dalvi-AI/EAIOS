/* Tasks — kanban board. Cards arrive automatically from meeting minutes
   ("action items" → todo cards) or are added manually; drag between columns
   or use the arrows. Assign to any online teammate. */
import { ArrowLeft, ArrowRight, Mic, Plus, SquareKanban, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { apiTaskCreate, apiTaskDelete, apiTaskPatch, apiTasks, type TaskRow } from "../lib/api";
import { useOS } from "../store";

const COLS: { id: TaskRow["status"]; label: string; hue: number }[] = [
  { id: "todo", label: "To do", hue: 210 }, { id: "doing", label: "In progress", hue: 38 }, { id: "done", label: "Done", hue: 150 },
];
const ORDER: TaskRow["status"][] = ["todo", "doing", "done"];

export default function TasksApp() {
  const me = useOS((s) => s.user);
  const online = useOS((s) => s.online);
  const [tasks, setTasks] = useState<TaskRow[]>([]);
  const [title, setTitle] = useState("");
  const [drag, setDrag] = useState<string | null>(null);

  useEffect(() => { apiTasks().then(setTasks).catch(() => {}); }, []);

  async function add() {
    const t = title.trim();
    if (t.length < 2) return;
    setTitle("");
    const created = await apiTaskCreate(t);
    setTasks((x) => [created, ...x]);
  }
  async function move(id: string, dir: 1 | -1) {
    const t = tasks.find((x) => x.id === id); if (!t) return;
    const next = ORDER[ORDER.indexOf(t.status) + dir]; if (!next) return;
    setTasks((x) => x.map((y) => (y.id === id ? { ...y, status: next } : y)));
    await apiTaskPatch(id, { status: next }).catch(() => {});
  }
  async function drop(status: TaskRow["status"]) {
    if (!drag) return;
    setTasks((x) => x.map((y) => (y.id === drag ? { ...y, status } : y)));
    await apiTaskPatch(drag, { status }).catch(() => {});
    setDrag(null);
  }
  async function assign(id: string, assignee_id: string) {
    const who = [...online, ...(me ? [{ id: me.id, name: me.full_name, hue: me.avatar_hue, role: me.role }] : [])].find((u) => u.id === assignee_id);
    setTasks((x) => x.map((y) => (y.id === id ? { ...y, assignee_id: assignee_id || null, assignee: who?.name ?? null } : y)));
    await apiTaskPatch(id, { assignee_id }).catch(() => {});
  }
  async function remove(id: string) {
    setTasks((x) => x.filter((y) => y.id !== id));
    await apiTaskDelete(id).catch(() => {});
  }

  const people = [...(me ? [{ id: me.id, name: `${me.full_name} (me)` }] : []), ...online.filter((u) => u.id !== me?.id).map((u) => ({ id: u.id, name: u.name }))];

  return (
    <div className="app-pane">
      <form className="app-toolbar" onSubmit={(e) => { e.preventDefault(); void add(); }}>
        <span className="pill info"><SquareKanban size={11} /> {tasks.length} tasks</span>
        <div className="field" style={{ flex: 1 }}>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a task… (or generate them from a meeting)" aria-label="New task title" />
        </div>
        <button className="btn primary sm" disabled={title.trim().length < 2}><Plus size={13} /> Add</button>
      </form>

      <div className="app-content kb-board">
        {COLS.map((col) => {
          const cards = tasks.filter((t) => t.status === col.id);
          return (
            <div key={col.id} className="kb-col" onDragOver={(e) => e.preventDefault()} onDrop={() => void drop(col.id)}>
              <div className="kb-col-head" style={{ "--hue": col.hue } as React.CSSProperties}>
                <span>{col.label}</span><span className="pill dim">{cards.length}</span>
              </div>
              {cards.map((t) => (
                <div key={t.id} className="kb-card" draggable onDragStart={() => setDrag(t.id)}>
                  <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.45 }}>{t.title}</p>
                  <div style={{ display: "flex", gap: 6, alignItems: "center", marginTop: 8, flexWrap: "wrap" }}>
                    {t.source === "meeting" && <span className="pill dim" title="Created from meeting minutes"><Mic size={9} /> meeting</span>}
                    <select className="plain" style={{ fontSize: 10.5, maxWidth: 130 }} value={t.assignee_id ?? ""} onChange={(e) => void assign(t.id, e.target.value)} aria-label="Assignee">
                      <option value="">Unassigned</option>
                      {people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                      {t.assignee_id && !people.some((p) => p.id === t.assignee_id) && <option value={t.assignee_id}>{t.assignee}</option>}
                    </select>
                    <span style={{ marginLeft: "auto", display: "flex", gap: 2 }}>
                      {col.id !== "todo" && <button className="mb-item" onClick={() => void move(t.id, -1)} aria-label="Move left"><ArrowLeft size={12} /></button>}
                      {col.id !== "done" && <button className="mb-item" onClick={() => void move(t.id, 1)} aria-label="Move right"><ArrowRight size={12} /></button>}
                      <button className="mb-item" onClick={() => void remove(t.id)} aria-label="Delete task"><Trash2 size={12} /></button>
                    </span>
                  </div>
                </div>
              ))}
              {cards.length === 0 && <p className="faint" style={{ fontSize: 11, textAlign: "center", padding: "18px 0" }}>Drop cards here</p>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
