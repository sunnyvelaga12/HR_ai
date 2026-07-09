"use client";

import { useState, useRef, useEffect, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Message {
  role: "user" | "assistant";
  content: string;
  error?: boolean;
}

interface QuickQuery {
  label: string;
  icon: string;
  topic: Topic;
  query: string;
}

type Topic = "all" | "leave" | "wfh" | "expenses" | "attendance" | "appraisal" | "conduct";

// ─── Constants ────────────────────────────────────────────────────────────────

const TOPICS: { id: Topic; label: string }[] = [
  { id: "all", label: "All" },
  { id: "leave", label: "Leave" },
  { id: "wfh", label: "WFH" },
  { id: "expenses", label: "Expenses" },
  { id: "attendance", label: "Attendance" },
  { id: "appraisal", label: "Appraisal" },
  { id: "conduct", label: "Conduct" },
];

const QUICK_QUERIES: QuickQuery[] = [
  {
    label: "Leave balance",
    icon: "📅",
    topic: "leave",
    query: "What are the different leave categories and how many days am I entitled to for each?",
  },
  {
    label: "WFH policy",
    icon: "🏠",
    topic: "wfh",
    query: "What is the work-from-home policy and who is eligible to apply?",
  },
  {
    label: "Expense claims",
    icon: "🧾",
    topic: "expenses",
    query: "How do I submit an expense claim and what expenses are covered?",
  },
  {
    label: "Attendance rules",
    icon: "⏰",
    topic: "attendance",
    query: "What are the office timings, core hours, and late arrival policy?",
  },
  {
    label: "Appraisal cycle",
    icon: "📈",
    topic: "appraisal",
    query: "How does the annual appraisal work and what are the rating guidelines?",
  },
  {
    label: "Dress code",
    icon: "👔",
    topic: "conduct",
    query: "What is the dress code for regular days and client visits?",
  },
];

const INITIAL_MESSAGE: Message = {
  role: "assistant",
  content:
    "Hello! I'm HRBot, TechNovance Solutions' official HR Policy Assistant.\n\nAsk me about leaves, WFH, expenses, attendance, holidays, dress code, appraisals, and more. I answer only from official company policy documents.",
};

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderMessageContent(content: string) {
  const blocks = content.split(/\n{2,}/g).filter(Boolean);

  return blocks.map((block, blockIndex) => {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    const isList = lines.every((line) => /^[-*•]\s+/.test(line));

    if (isList) {
      return (
        <ul key={blockIndex} className="ml-4 list-disc space-y-1 text-sm leading-7 text-slate-700 dark:text-slate-300">
          {lines.map((line, lineIndex) => (
            <li key={lineIndex}>{line.replace(/^[-*•]\s+/, "")}</li>
          ))}
        </ul>
      );
    }

    return (
      <p key={blockIndex} className="mb-3 last:mb-0 text-sm leading-7 text-slate-800 dark:text-slate-200">
        {lines.map((line, lineIndex) => (
          <span key={lineIndex}>
            {line}
            {lineIndex < lines.length - 1 ? <br /> : null}
          </span>
        ))}
      </p>
    );
  });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-3 py-2.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 w-fit">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-pulse"
          style={{ animationDelay: `${i * 200}ms` }}
        />
      ))}
    </div>
  );
}

interface MessageBubbleProps {
  message: Message;
  timestamp: Date;
}

function MessageBubble({ message, timestamp }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-2.5 items-start ${isUser ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`
          flex-shrink-0 w-7 h-7 rounded-full border text-[11px] font-medium
          flex items-center justify-center select-none
          ${isUser
            ? "border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
            : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 text-slate-500 dark:text-slate-400"
          }
        `}
        aria-hidden="true"
      >
        {isUser ? "You" : "HR"}
      </div>

      {/* Bubble + meta */}
      <div className={`flex flex-col gap-1 max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`
            px-4 py-3.5 rounded-3xl border shadow-sm text-[14px] leading-7
            ${isUser
              ? "bg-blue-500 text-white border-blue-500 shadow-blue-500/10"
              : message.error
              ? "bg-rose-50 text-rose-900 border-rose-200 dark:bg-rose-950 dark:text-rose-100 dark:border-rose-800"
              : "bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100"
            }
          `}
        >
          {renderMessageContent(message.content)}
        </div>
        <p className="text-[10px] text-slate-400 dark:text-slate-600 px-1">
          {isUser ? `You · ${formatTime(timestamp)}` : "HRBot · policy assistant"}
        </p>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function Home() {
  // Redirect based on role after auth
  useEffect(() => {
    const role = typeof window !== "undefined" ? localStorage.getItem("role") : null;
    if (role === "hr_admin") window.location.href = "/hr";
    else if (role === "employee") window.location.href = "/employees";
    else window.location.href = "/login";
  }, []);

  // Keep existing UI for now; will typically never render due to redirect.
  const [messages, setMessages] = useState<Message[]>([INITIAL_MESSAGE]);

  const [timestamps, setTimestamps] = useState<Date[]>([new Date()]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTopic, setActiveTopic] = useState<Topic>("all");
  const [search, setSearch] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      const userMsg: Message = { role: "user", content: trimmed };
      const now = new Date();

      setMessages((prev) => [...prev, userMsg]);
      setTimestamps((prev) => [...prev, now]);
      setInput("");
      setIsLoading(true);

      try {
        const history = [...messages, userMsg].map(({ role, content }) => ({ role, content }));

        const res = await fetch(`${BACKEND_URL}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: trimmed, history }),
        });

        const contentType = res.headers.get("content-type");
        let data: any = {};
        if (contentType && contentType.includes("application/json")) {
          data = await res.json();
        } else {
          const text = await res.text();
          throw new Error(`Server error: ${res.status} - ${text.substring(0, 100)}...`);
        }

        if (!res.ok) {
          throw new Error(data.detail ?? data.error ?? "Unknown server error");
        }

        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.response ?? "Sorry, I couldn't generate a response at this time.",
            error: Boolean(data.error),
          },
        ]);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `I couldn't reach the backend at ${BACKEND_URL}. Please verify it's running.\n\nError: ${msg}`,
            error: true,
          },
        ]);
      } finally {
        setIsLoading(false);
        setTimestamps((prev) => [...prev, new Date()]);
        inputRef.current?.focus();
      }
    },
    [isLoading, messages]
  );

  const filteredQueries = QUICK_QUERIES.filter(
    (q) =>
      (activeTopic === "all" || q.topic === activeTopic) &&
      (!search || q.label.toLowerCase().includes(search.toLowerCase()) || q.query.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="min-h-screen bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
      <div className="max-w-[1400px] mx-auto px-5 py-5 flex flex-col gap-5">

        {/* ── Header ── */}
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-center text-[12px] font-medium text-slate-500 dark:text-slate-400 select-none flex-shrink-0">
              HR
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600">HR Studio</p>
              <h1 className="text-[17px] font-medium">Policy assist</h1>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-6" aria-label="Primary">
            {["Dashboard", "Documents", "Analytics"].map((label) => (
              <a
                key={label}
                href="#"
                className="text-[13px] text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors"
              >
                {label}
              </a>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <span className="text-[11px] px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-800 text-slate-400 dark:text-slate-600">
              Beta
            </span>
            {/* <div
              className="w-8 h-8 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-center text-[11px] font-medium text-slate-500 dark:text-slate-400 select-none"
              aria-label="TechNovance Solutions"
            >
              TS
            </div> */}
          </div>
        </header>

        {/* ── Body ── */}
        <div className="grid lg:grid-cols-[272px_1fr] gap-5 items-start">

          {/* ── Sidebar ── */}
          <aside className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 flex flex-col gap-5" aria-label="Sidebar">
            {/* Search */}
            <div>
              <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-2.5">Search</p>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter policy topics…"
                aria-label="Search policy topics"
                className="w-full px-3 py-2 text-[13px] rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300 dark:focus:ring-slate-700"
              />
            </div>

            {/* Topic filters */}
            <div>
              <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-2.5">Topics</p>
              <div className="flex flex-wrap gap-1.5">
                {TOPICS.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTopic(t.id)}
                    className={`
                      text-[12px] px-2.5 py-1 rounded-md border transition-colors
                      ${activeTopic === t.id
                        ? "border-slate-400 dark:border-slate-500 bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                        : "border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700 hover:text-slate-800 dark:hover:text-slate-200"
                      }
                    `}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="h-px bg-slate-100 dark:bg-slate-800" />

            {/* Quick actions */}
            <div>
              <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-2.5">Quick actions</p>
              <div className="flex flex-col gap-1.5">
                {filteredQueries.length === 0 ? (
                  <p className="text-[12px] text-slate-400 dark:text-slate-600 px-1">No matching actions.</p>
                ) : (
                  filteredQueries.map((item, i) => (
                    <button
                      key={i}
                      onClick={() => sendMessage(item.query)}
                      className="flex flex-col gap-0.5 px-3 py-2.5 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 hover:border-slate-200 dark:hover:border-slate-700 hover:bg-white dark:hover:bg-slate-900 text-left transition-colors w-full"
                    >
                      <span className="text-[13px] font-medium text-slate-700 dark:text-slate-300">
                        {item.icon} {item.label}
                      </span>
                      <span className="text-[11px] text-slate-400 dark:text-slate-600 line-clamp-1">
                        {item.query}
                      </span>
                    </button>
                  ))
                )}
              </div>
            </div>
          </aside>

          {/* ── Right column ── */}
          <main className="flex flex-col gap-5">

            {/* Info cards */}
            <div className="grid sm:grid-cols-2 gap-3">
              {[
                {
                  title: "How to use",
                  body: "Ask one policy topic at a time for best results. HRBot answers only from official company policy documents.",
                },
                // {
                //   title: "Response caching",
                //   body: "Repeated queries are served faster. Responses are grounded in TechNovance HR policy — no hallucinations.",
                // },
              ].map((card) => (
                <div
                  key={card.title}
                  className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-3.5"
                >
                  <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-2">{card.title}</p>
                  <p className="text-[13px] text-slate-600 dark:text-slate-400 leading-relaxed">{card.body}</p>
                </div>
              ))}
            </div>

            {/* Chat panel */}
            <section
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl flex flex-col overflow-hidden"
              aria-label="HRBot conversation"
            >
              {/* Chat header */}
              <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-1">Chat module</p>
                  <h2 className="text-[17px] font-medium">HRBot conversation</h2>
                </div>
                {/* <div className="flex items-center gap-1.5 text-[12px] text-slate-500 dark:text-slate-400 px-2.5 py-1.5 rounded-md border border-slate-100 dark:border-slate-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" aria-hidden="true" />
                  Groq · Llama 3.1
                </div> */}
              </div>

              {/* Messages */}
              <div
                className="flex-1 px-5 py-4 flex flex-col gap-4 overflow-y-auto max-h-[420px] min-h-[180px]"
                role="log"
                aria-live="polite"
                aria-label="Conversation messages"
              >
                {messages.map((msg, i) => (
                  <MessageBubble key={i} message={msg} timestamp={timestamps[i] ?? new Date()} />
                ))}
                {isLoading && (
                  <div className="flex gap-2.5 items-start">
                    <div className="flex-shrink-0 w-7 h-7 rounded-full border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 flex items-center justify-center text-[11px] text-slate-500 select-none" aria-hidden="true">
                      HR
                    </div>
                    <TypingIndicator />
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input */}
              <div className="px-4 py-3.5 border-t border-slate-100 dark:border-slate-800 flex gap-2.5 items-center">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage(input);
                    }
                  }}
                  placeholder="Ask a policy question, e.g. 'Can I carry forward leave?'"
                  aria-label="Type your HR policy question"
                  disabled={isLoading}
                  className="flex-1 px-3.5 py-2 text-[13px] rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-300 dark:focus:ring-slate-700 disabled:opacity-50"
                />
                <button
                  onClick={() => sendMessage(input)}
                  disabled={isLoading || !input.trim()}
                  aria-label="Send message"
                  className="px-4 py-2 text-[13px] font-medium rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-700 dark:hover:bg-slate-100 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  Send →
                </button>
              </div>
            </section>
          </main>
        </div>
      </div>
    </div>
  );
}