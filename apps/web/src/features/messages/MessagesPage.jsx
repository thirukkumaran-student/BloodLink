import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
  Textarea,
  useToast
} from "@bloodlink/ui";
import { conversationApi } from "../../api/endpoints";
import { queryKeys } from "../../app/hooks";
import { relativeTime } from "../../lib/format";
import { CLINICAL_DISCLAIMER } from "../../lib/capabilities";
function MessagesPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState(null);
  const [draft, setDraft] = useState("");
  const endRef = useRef(null);
  const threads = useQuery({ queryKey: queryKeys.conversations, queryFn: conversationApi.list });
  const thread = useQuery({
    queryKey: ["conversation", activeId],
    queryFn: () => conversationApi.read(activeId),
    enabled: Boolean(activeId),
    refetchInterval: 15e3
  });
  const send = useMutation({
    mutationFn: (content) => conversationApi.send(activeId, content),
    onSuccess: async () => {
      setDraft("");
      await thread.refetch();
      await queryClient.invalidateQueries({ queryKey: queryKeys.conversations });
    }
  });
  useEffect(() => {
    if (!threads.data?.items.length) return;
    setActiveId((current) => current ?? threads.data.items[0].id);
  }, [threads.data]);
  useEffect(() => {
    if (activeId) void conversationApi.markRead(activeId);
    endRef.current?.scrollIntoView({ block: "end" });
  }, [activeId, thread.data?.messages.length]);
  return <><PageHeader
    title="Coordination threads"
    subtitle="Threads exist only inside a specific request — with the hospital, the donor or the blood centre involved."
  />{threads.isLoading ? <LoadingState label="Loading threads…" /> : null}{threads.error ? <ErrorState message={threads.error.message} onRetry={() => threads.refetch()} /> : null}{threads.data && !threads.data.items.length ? <EmptyState
    title="No coordination threads yet"
    hint="A thread appears once you accept a request (donor) or a donor/blood centre responds to one of yours (hospital)."
  /> : null}{threads.data?.items.length ? <div className="bl-grid" style={{ gridTemplateColumns: "320px minmax(0, 1fr)" }}><Card flush title="Threads"><div className="bl-stack-sm" style={{ padding: "var(--bl-space-3)" }}>{threads.data.items.map((item) => <button
    key={item.id}
    type="button"
    className={`bl-dropdown__item${item.id === activeId ? " bl-app__nav-link--active" : ""}`}
    onClick={() => setActiveId(item.id)}
  ><div className="bl-row-between"><strong>{item.counterpartyName}</strong>{item.unreadCount ? <Badge tone="danger">{item.unreadCount}</Badge> : null}</div><div className="bl-subtle">{item.counterpartyRole} · {item.requestReference ?? item.bloodRequestId.slice(0, 8)}</div><div className="bl-subtle">{item.lastMessagePreview ?? "No messages yet"}</div></button>)}</div></Card><Card
    title={thread.data?.conversation.counterpartyName ?? "Thread"}
    subtitle={thread.data ? <span className="bl-row" style={{ gap: "var(--bl-space-2)" }}><span>Request {thread.data.conversation.requestReference}</span>{thread.data.conversation.requestStatus ? <StatusBadge status={thread.data.conversation.requestStatus} /> : null}</span> : void 0}
  >{thread.isLoading ? <LoadingState /> : thread.error ? <ErrorState message={thread.error.message} onRetry={() => thread.refetch()} /> : <div className="bl-stack"><div className="bl-stack-sm" style={{ maxHeight: 420, overflowY: "auto" }}>{(thread.data?.messages ?? []).map((message) => <div
    key={message.id}
    className="bl-notice"
    style={{
      borderLeftColor: message.mine ? "var(--bl-color-primary)" : "var(--bl-color-border-strong)",
      background: message.mine ? "var(--bl-color-primary-soft)" : void 0
    }}
  ><div>{message.content}</div><div className="bl-subtle">{message.mine ? "You" : thread.data?.conversation.counterpartyName} ·{" "}{relativeTime(message.createdAt)}</div></div>)}<div ref={endRef} /></div><Textarea
    placeholder="Coordination only — never share patient details or addresses here."
    value={draft}
    onChange={(event) => setDraft(event.target.value)}
    maxLength={2e3}
  /><div className="bl-row-between"><span className="bl-subtle">{CLINICAL_DISCLAIMER}</span><Button
    variant="primary"
    disabled={!draft.trim()}
    loading={send.isPending}
    onClick={async () => {
      try {
        await send.mutateAsync(draft.trim());
      } catch (caught) {
        toast.error("Message not sent", caught.message);
      }
    }}
  >
                    Send
                  </Button></div></div>}</Card></div> : null}</>;
}
export {
  MessagesPage
};
