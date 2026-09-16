import {
  ChevronRight,
  FolderOpen,
  Hash,
  Users,
  MoreHorizontal,
  Pencil,
  MessagesSquare,
  Plus,
  Search,
  Settings2,
  Trash2,
  ChevronDown,
  SlidersHorizontal,
} from "lucide-react";
import { cx, IconButton } from "./ui";

// Project tree: the selected project is open, the others are collapsed.
export function Sidebar({
  project,
  projects,
  selectProject,
  editProject,
  locked,
  mobile,
  conversations,
  cid,
  view,
  navigate,
  openConversation,
  newConversation,
  openTrash,
  conversationMenu,
  openConversationMenu,
}) {
  const pages = [
    ["settings", "Models", Users],
    ["project", "Setup", SlidersHorizontal],
    ["archive", "Search", Search],
  ];
  return (
    <aside className={cx("sidebar", mobile && "open")}>
      <div className="brand">
        <div className="brandmark">m</div>
        <strong>Mother</strong>
      </div>
      <div className="sidebar-scroll">
        <div className="section-label">
          <span>Projects</span>
          <IconButton title="New project" onClick={() => editProject()}>
            <Plus size={16} />
          </IconButton>
        </div>
        <div className="tree" aria-label="Projects">
          {projects.map((p) => {
            const open = p.id === project.id;
            return (
              <div key={p.id} className={cx("tree-project", open && "open")}>
                <div className={cx("tree-row", open && "selected")}>
                  <button
                    aria-expanded={open}
                    disabled={!open && locked}
                    title={
                      !open && locked
                        ? "Wait for the current reply to finish"
                        : p.name
                    }
                    onClick={() => !open && selectProject(p.id)}
                  >
                    {open ? (
                      <ChevronDown size={15} />
                    ) : (
                      <ChevronRight size={15} />
                    )}
                    <FolderOpen size={16} />
                    <span className="nav-name">{p.name}</span>
                    {p.is_main && <span className="tree-tag">Main</span>}
                  </button>
                  {open && !p.is_main && (
                    <IconButton
                      title="Rename project"
                      onClick={() => editProject(p)}
                    >
                      <Pencil size={13} />
                    </IconButton>
                  )}
                </div>
                {open && (
                  <div className="tree-children">
                    <div
                      className={cx("tree-row", view === "board" && "selected")}
                    >
                      <button onClick={() => navigate("board")}>
                        <MessagesSquare size={16} />
                        <span className="nav-name">Chat</span>
                      </button>
                      <IconButton
                        title="New conversation"
                        onClick={newConversation}
                      >
                        <Plus size={14} />
                      </IconButton>
                    </div>
                    <div className="tree-children">
                      {conversations.map((c) => (
                        <div
                          key={c.id}
                          className={cx(
                            "tree-row",
                            cid === c.id && view === "board" && "current",
                          )}
                        >
                          <button
                            title={c.title}
                            onClick={() => openConversation(c.id)}
                          >
                            <Hash size={15} />
                            <span className="nav-name">{c.title}</span>
                          </button>
                          <IconButton
                            title={`Options for ${c.title}`}
                            aria-haspopup="menu"
                            aria-expanded={conversationMenu?.id === c.id}
                            onClick={(e) => openConversationMenu(c, e)}
                          >
                            <MoreHorizontal size={16} />
                          </IconButton>
                        </div>
                      ))}
                      {!conversations.length && (
                        <div className="tree-row muted">
                          <button onClick={newConversation}>
                            <Plus size={14} />
                            <span className="nav-name">
                              Start a conversation
                            </span>
                          </button>
                        </div>
                      )}
                    </div>
                    {pages.map(([key, label, Icon]) => (
                      <div
                        key={key}
                        className={cx("tree-row", view === key && "selected")}
                      >
                        <button onClick={() => navigate(key)}>
                          <Icon size={16} />
                          <span className="nav-name">{label}</span>
                        </button>
                      </div>
                    ))}
                    <div className="tree-row">
                      <button onClick={openTrash}>
                        <Trash2 size={16} />
                        <span className="nav-name">Trash</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <nav className="bottom-nav">
        <button
          className={cx(view === "system" && "selected")}
          onClick={() => navigate("system")}
        >
          <Settings2 size={18} />
          System setup
        </button>
      </nav>
      <div className="local-footer">
        <span className="status-dot" /> {project.name}
      </div>
    </aside>
  );
}
