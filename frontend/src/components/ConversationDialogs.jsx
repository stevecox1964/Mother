import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  Pencil,
  RotateCcw,
  Trash2,
  X,
} from "lucide-react";
import { saveToFile } from "../utils/saveToFile";
import { IconButton, Field, Dialog } from "./ui";

// Owns the conversation row menu, rename, trash and new-conversation dialogs.
export function useConversationActions({
  api,
  refreshList,
  fail,
  navigate,
  create,
  selectedRef,
  reset,
}) {
  const [conversationMenu, setConversationMenu] = useState(null),
    [renaming, setRenaming] = useState(null),
    [renameTitle, setRenameTitle] = useState(""),
    [trash, setTrash] = useState(null),
    [newOpen, setNewOpen] = useState(false),
    [newTitle, setNewTitle] = useState(""),
    [actionBusy, setActionBusy] = useState(false),
    [actionError, setActionError] = useState("");
  const menuRef = useRef(),
    menuTrigger = useRef();
  useEffect(() => {
    if (conversationMenu)
      menuRef.current?.querySelector('[role="menuitem"]')?.focus();
  }, [conversationMenu]);
  const closeMenu = () => {
    setConversationMenu(null);
    menuTrigger.current?.focus();
  };
  const openMenu = (conversation, event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    menuTrigger.current = event.currentTarget;
    setConversationMenu({
      ...conversation,
      x: Math.max(8, Math.min(rect.right - 185, window.innerWidth - 193)),
      y: Math.max(8, Math.min(rect.bottom + 5, window.innerHeight - 150)),
    });
  };
  const openTrash = async () => {
    try {
      setTrash(await api("/trash"));
      setActionError("");
    } catch (e) {
      fail(e);
    }
  };
  const removeConversation = async (conversation) => {
    closeMenu();
    try {
      await api("/conversations/" + conversation.id, "DELETE", {});
      const list = await api("/conversations");
      refreshList(list);
      if (selectedRef.current === conversation.id) reset(list[0]?.id || null);
    } catch (e) {
      fail(e);
    }
  };
  const exportConversation = async (conversation) => {
    closeMenu();
    try {
      const data = await api("/conversations/" + conversation.id);
      saveToFile(
        data.events
          .filter((e) => e.kind !== "run")
          .map((e) => `[${e.created_at}] ${e.author} · ${e.kind}\n${e.content}`)
          .join("\n\n"),
        "mother",
      );
    } catch (e) {
      fail(e);
    }
  };
  const dialogs = (
    <>
      {conversationMenu && (
        <>
          <button
            className="menu-backdrop"
            aria-label="Close conversation menu"
            onClick={closeMenu}
          />
          <div
            className="conversation-menu"
            role="menu"
            aria-label="Conversation actions"
            ref={menuRef}
            style={{ left: conversationMenu.x, top: conversationMenu.y }}
            onKeyDown={(e) => {
              const items = Array.from(
                e.currentTarget.querySelectorAll('[role="menuitem"]'),
              );
              const index = items.indexOf(document.activeElement);
              if (e.key === "Escape" || e.key === "Tab") {
                e.preventDefault();
                closeMenu();
              }
              if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
                e.preventDefault();
                items[
                  e.key === "Home"
                    ? 0
                    : e.key === "End"
                      ? items.length - 1
                      : (index +
                          (e.key === "ArrowDown" ? 1 : -1) +
                          items.length) %
                        items.length
                ]?.focus();
              }
            }}
          >
            <button
              role="menuitem"
              onClick={() => {
                setRenaming(conversationMenu);
                setRenameTitle(conversationMenu.title);
                setActionError("");
                closeMenu();
              }}
            >
              <Pencil size={15} />
              Rename
            </button>
            <button
              role="menuitem"
              onClick={() => exportConversation(conversationMenu)}
            >
              <ArrowDownToLine size={15} />
              Export transcript
            </button>
            <button
              role="menuitem"
              className="danger"
              onClick={() => removeConversation(conversationMenu)}
            >
              <Trash2 size={15} />
              Delete
            </button>
          </div>
        </>
      )}
      {renaming && (
        <Dialog
          label="Rename conversation"
          onClose={() => !actionBusy && setRenaming(null)}
        >
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              if (actionBusy || !renameTitle.trim()) return;
              setActionBusy(true);
              setActionError("");
              try {
                await api("/conversations/" + renaming.id, "PUT", {
                  title: renameTitle.trim(),
                });
                await refreshList();
                setRenaming(null);
              } catch (e) {
                setActionError(e.message);
              } finally {
                setActionBusy(false);
              }
            }}
          >
            <div className="modal-heading">
              <h2>Rename conversation</h2>
              <IconButton
                type="button"
                title="Close rename"
                disabled={actionBusy}
                onClick={() => setRenaming(null)}
              >
                <X size={18} />
              </IconButton>
            </div>
            <Field label="Conversation name">
              <input
                autoFocus
                required
                maxLength={160}
                value={renameTitle}
                onChange={(e) => setRenameTitle(e.target.value)}
              />
            </Field>
            {actionError && (
              <p className="dialog-error" role="alert">
                {actionError}
              </p>
            )}
            <div className="dialog-actions">
              <button
                className="secondary"
                type="button"
                disabled={actionBusy}
                onClick={() => setRenaming(null)}
              >
                Cancel
              </button>
              <button
                className="primary"
                disabled={actionBusy || !renameTitle.trim()}
              >
                {actionBusy ? "Saving…" : "Save name"}
              </button>
            </div>
          </form>
        </Dialog>
      )}
      {trash !== null && (
        <Dialog label="Trash" onClose={() => !actionBusy && setTrash(null)}>
          <div className="modal-heading">
            <h2>Trash</h2>
            <IconButton
              title="Close trash"
              disabled={actionBusy}
              onClick={() => setTrash(null)}
            >
              <X size={18} />
            </IconButton>
          </div>
          <p>Deleted conversations stay here until you restore them.</p>
          {actionError && (
            <p className="dialog-error" role="alert">
              {actionError}
            </p>
          )}
          <div className="trash-list">
            {!trash.length && <p>Trash is empty.</p>}
            {trash.map((c) => (
              <div className="trash-row" key={c.id}>
                <span>{c.title}</span>
                <button
                  className="secondary"
                  disabled={actionBusy}
                  aria-label={`Restore ${c.title}`}
                  onClick={async () => {
                    setActionBusy(true);
                    setActionError("");
                    try {
                      await api(
                        "/conversations/" + c.id + "/restore",
                        "POST",
                        {},
                      );
                      await refreshList();
                      setTrash(await api("/trash"));
                    } catch (e) {
                      setActionError(e.message);
                    } finally {
                      setActionBusy(false);
                    }
                  }}
                >
                  <RotateCcw size={14} />
                  Restore
                </button>
              </div>
            ))}
          </div>
        </Dialog>
      )}
      {newOpen && (
        <Dialog label="Start a conversation" onClose={() => setNewOpen(false)}>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await create(newTitle || "New conversation");
                setNewTitle("");
                setNewOpen(false);
                navigate("board");
              } catch (e) {
                fail(e);
              }
            }}
          >
            <div className="modal-heading">
              <h2>Start a conversation</h2>
              <IconButton
                title="Close"
                type="button"
                onClick={() => setNewOpen(false)}
              >
                <X size={18} />
              </IconButton>
            </div>
            <p>A fresh board for the next thing you want to figure out.</p>
            <Field label="Conversation name">
              <input
                autoFocus
                value={newTitle}
                maxLength={160}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="What are we working on?"
              />
            </Field>
            <button className="primary" type="submit">
              Create conversation
              <ArrowRight size={15} />
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
  return {
    conversationMenu,
    openMenu,
    openTrash,
    newConversation: () => setNewOpen(true),
    dialogs,
  };
}
