import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import {
	AlertCircle,
	LoaderCircle,
	Menu,
	Pencil,
	Plus,
	SendHorizontal,
	Trash2,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import {
	createConversation,
	deleteConversation,
	getConversation,
	listConversations,
	renameConversation,
	sendConversationMessage,
} from "../services/api";
import type { ChatDetails, Conversation, ConversationSummary } from "../types";

const currency = new Intl.NumberFormat("en-US", {
	style: "currency",
	currency: "USD",
	minimumFractionDigits: 2,
	maximumFractionDigits: 4,
});

export default function Chat() {
	const [conversations, setConversations] = useState<ConversationSummary[]>([]);
	const [active, setActive] = useState<Conversation | null>(null);
	const [draft, setDraft] = useState("");
	const [listError, setListError] = useState<string | null>(null);
	const [sendError, setSendError] = useState<string | null>(null);
	const [isLoadingList, setIsLoadingList] = useState(true);
	const [isSending, setIsSending] = useState(false);
	const [showHistory, setShowHistory] = useState(false);
	const [editingId, setEditingId] = useState<string | null>(null);
	const [titleDraft, setTitleDraft] = useState("");
	const threadRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		void loadConversations();
	}, []);

	useEffect(() => {
		const thread = threadRef.current;
		if (thread) {
			thread.scrollTop = thread.scrollHeight;
		}
	}, [active?.messages, isSending]);

	async function loadConversations() {
		setIsLoadingList(true);
		try {
			setConversations(await listConversations());
			setListError(null);
		} catch (error) {
			setListError(error instanceof Error ? error.message : "Conversations could not be loaded.");
		} finally {
			setIsLoadingList(false);
		}
	}

	async function openConversation(id: string) {
		setShowHistory(false);
		setSendError(null);
		try {
			setActive(await getConversation(id));
			setListError(null);
		} catch (error) {
			setListError(error instanceof Error ? error.message : "That conversation could not be opened.");
		}
	}

	async function startConversation() {
		setSendError(null);
		try {
			const created = await createConversation();
			setConversations((current) => [created, ...current.filter((item) => item.id !== created.id)]);
			setActive(created);
			setShowHistory(false);
			setListError(null);
		} catch (error) {
			setListError(error instanceof Error ? error.message : "A new conversation could not be started.");
		}
	}

	async function saveTitle(id: string) {
		const title = titleDraft.trim();
		setEditingId(null);
		if (!title) return;
		try {
			const updated = await renameConversation(id, title);
			setConversations((current) => current.map((item) => (
				item.id === id ? { ...item, title: updated.title, updated_at: updated.updated_at } : item
			)));
			setActive((current) => current?.id === id ? { ...current, title: updated.title } : current);
		} catch (error) {
			setListError(error instanceof Error ? error.message : "The conversation could not be renamed.");
		}
	}

	async function removeConversation(id: string) {
		try {
			await deleteConversation(id);
			setConversations((current) => current.filter((item) => item.id !== id));
			setActive((current) => current?.id === id ? null : current);
		} catch (error) {
			setListError(error instanceof Error ? error.message : "The conversation could not be deleted.");
		}
	}

	async function submitMessage() {
		const message = draft.trim();
		if (!message || isSending) return;
		setIsSending(true);
		setSendError(null);
		try {
			let conversation = active;
			if (!conversation) {
				conversation = await createConversation();
			}
			const result = await sendConversationMessage(conversation.id, message);
			setDraft("");
			setActive(result.conversation);
			setConversations((current) => {
				const summary: ConversationSummary = {
					id: result.conversation.id,
					title: result.conversation.title,
					created_at: result.conversation.created_at,
					updated_at: result.conversation.updated_at,
					preview: result.conversation.messages.at(-1)?.content.slice(0, 80) ?? null,
				};
				return [summary, ...current.filter((item) => item.id !== summary.id)];
			});
		} catch (error) {
			setSendError(error instanceof Error ? error.message : "The message could not be sent.");
		} finally {
			setIsSending(false);
		}
	}

	function onSubmit(event: FormEvent) {
		event.preventDefault();
		void submitMessage();
	}

	function onDraftKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
		if (event.key === "Enter" && !event.shiftKey) {
			event.preventDefault();
			void submitMessage();
		}
	}

	return (
		<div className={`chat-page${showHistory ? " chat-page--history" : ""}`}>
			<aside className="chat-history" aria-label="Conversation history">
				<div className="chat-history__header">
					<button className="chat-new" type="button" onClick={() => void startConversation()}>
						<Plus size={16} />
						<span>New chat</span>
					</button>
				</div>
				{listError ? <p className="chat-inline-error" role="alert">{listError}</p> : null}
				<div className="chat-history__list">
					{isLoadingList ? <p className="chat-muted">Loading conversations</p> : null}
					{!isLoadingList && conversations.length === 0 ? <p className="chat-muted">No conversations yet.</p> : null}
					{conversations.map((conversation) => (
						<div className={`chat-history__item${active?.id === conversation.id ? " chat-history__item--active" : ""}`} key={conversation.id}>
							{editingId === conversation.id ? (
								<input
									className="chat-rename"
									value={titleDraft}
									aria-label="Conversation title"
									onChange={(event) => setTitleDraft(event.target.value)}
									onBlur={() => void saveTitle(conversation.id)}
									onKeyDown={(event) => {
										if (event.key === "Enter") void saveTitle(conversation.id);
										if (event.key === "Escape") setEditingId(null);
									}}
									autoFocus
								/>
							) : (
								<button className="chat-history__open" type="button" onClick={() => void openConversation(conversation.id)}>
									<strong>{conversation.title}</strong>
									<span>{conversation.preview || "Empty conversation"}</span>
								</button>
							)}
							<div className="chat-history__actions">
								<button
									type="button"
									aria-label={`Rename ${conversation.title}`}
									onClick={() => {
										setEditingId(conversation.id);
										setTitleDraft(conversation.title);
									}}
								>
									<Pencil size={14} />
								</button>
								<button type="button" aria-label={`Delete ${conversation.title}`} onClick={() => void removeConversation(conversation.id)}>
									<Trash2 size={14} />
								</button>
							</div>
						</div>
					))}
				</div>
			</aside>

			<section className="chat-thread" aria-label="Chat">
				<div className="chat-thread__bar">
					<button className="chat-history-toggle" type="button" onClick={() => setShowHistory((current) => !current)}>
						<Menu size={16} />
						<span>{showHistory ? "Hide history" : "History"}</span>
					</button>
					<strong>{active?.title ?? "Chat"}</strong>
				</div>
				<div className="chat-messages" ref={threadRef}>
					{!active || active.messages.length === 0 ? (
						<div className="chat-empty">
							<strong>Ask the routing gateway</strong>
							<p>Messages go through the existing gateway. The model tier, quality check, and cost stay attached to each reply.</p>
						</div>
					) : null}
					{active?.messages.map((message) => (
						<article className={`chat-bubble chat-bubble--${message.role}`} key={message.id}>
							<span className="chat-bubble__role">{message.role === "user" ? "You" : "Switchboard"}</span>
							{message.role === "assistant" ? (
								<div className="chat-markdown">
									<ReactMarkdown
										components={{
											a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer">{children}</a>,
											img: ({ alt }) => <span>{alt || "image"}</span>,
										}}
									>
										{message.content}
									</ReactMarkdown>
								</div>
							) : <p>{message.content}</p>}
							{message.role === "assistant" && message.details ? <RequestDetails details={message.details} /> : null}
						</article>
					))}
					{isSending ? (
						<div className="chat-bubble chat-bubble--assistant chat-bubble--pending" role="status">
							<LoaderCircle size={16} className="spin" />
							<span>Waiting for the gateway</span>
						</div>
					) : null}
				</div>
				{sendError ? (
					<div className="notice" role="alert">
						<AlertCircle size={16} />
						<span>{sendError}</span>
					</div>
				) : null}
				<form className="chat-composer" onSubmit={onSubmit}>
					<textarea
						value={draft}
						rows={3}
						placeholder="Send a message"
						aria-label="Message"
						onChange={(event) => setDraft(event.target.value)}
						onKeyDown={onDraftKeyDown}
						disabled={isSending}
					/>
					<button type="submit" disabled={isSending || draft.trim().length === 0}>
						{isSending ? <LoaderCircle size={16} className="spin" /> : <SendHorizontal size={16} />}
						<span>Send</span>
					</button>
				</form>
			</section>
		</div>
	);
}

function RequestDetails({ details }: { details: ChatDetails }) {
	const rows = detailRows(details);
	if (rows.length === 0) return null;
	return (
		<details className="chat-details">
			<summary>Request details</summary>
			<dl>
				{rows.map((row) => (
					<div key={row.label}>
						<dt>{row.label}</dt>
						<dd>{row.value}</dd>
					</div>
				))}
			</dl>
		</details>
	);
}

function detailRows(details: ChatDetails): { label: string; value: string }[] {
	const rows: { label: string; value: string }[] = [];
	if (details.model_tier) rows.push({ label: "Model tier", value: details.model_tier });
	if (details.actual_model) rows.push({ label: "Actual model", value: details.actual_model });
	if (details.complexity) rows.push({ label: "Complexity", value: details.complexity });
	if (details.quality_score != null || details.quality_status) {
		const score = details.quality_score == null ? "" : ` ${details.quality_score}`;
		rows.push({ label: "Quality", value: `${details.quality_status ?? "recorded"}${score}`.trim() });
	}
	if (details.quality_relevant) rows.push({ label: "Relevant", value: details.quality_relevant });
	if (details.quality_complete) rows.push({ label: "Complete", value: details.quality_complete });
	if (details.quality_escalate) rows.push({ label: "Escalate", value: details.quality_escalate });
	if (details.latency_ms != null) rows.push({ label: "Latency", value: `${Math.round(details.latency_ms)} ms` });
	if (details.input_tokens != null || details.output_tokens != null) {
		rows.push({
			label: "Tokens",
			value: `${details.input_tokens ?? 0} in / ${details.output_tokens ?? 0} out`,
		});
	}
	if (details.estimated_cost != null) rows.push({ label: "Cost", value: currency.format(details.estimated_cost) });
	if (details.cache_hit != null) rows.push({ label: "Cache", value: details.cache_hit ? "Hit" : "Miss" });
	if (details.escalated != null) rows.push({ label: "Escalated", value: details.escalated ? "Yes" : "No" });
	if (details.fallback_used) rows.push({ label: "Fallback", value: "Yes" });
	if (details.routing_reason) rows.push({ label: "Routing", value: details.routing_reason });
	return rows;
}
