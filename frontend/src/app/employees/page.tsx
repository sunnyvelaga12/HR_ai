"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { useRouter } from "next/navigation";

const BACKEND_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:9000";

type Message = { role: "user" | "assistant"; content: string; error?: boolean };
type Tab = "overview" | "attendance" | "leaves" | "profile" | "search" | "chatbot";

const TAB_LABELS: Record<Tab, string> = {
  overview: "Overview",
  attendance: "Attendance",
  leaves: "Leaves",
  profile: "Profile",
  search: "Search Policies",
  chatbot: "AI Policy Assist",
};

interface EmployeeProfile {
  employee_id: string;
  first_name: string;
  last_name: string;
  email: string;
  department: string;
  designation: string;
  manager_name: string;
  office_location: string;
  work_mode: string;
  years_with_company: number;
  performance_rating: number;
  phone?: string;
  skills?: string[];
  certifications?: string[];
  date_of_joining?: string;
}

interface LeaveBalance {
  casual_leave_remaining: number;
  sick_leave_remaining: number;
  privilege_leave_remaining: number;
  floating_holidays_remaining: number;
}

interface AttendanceRecord {
  date: string;
  status: string;
  hours_worked: number;
}

// ─── Tailwind Chatbot Helper Components ───────────────────────────────────────

type Topic = "all" | "leave" | "wfh" | "expenses" | "attendance" | "appraisal" | "conduct";

const TOPICS: { id: Topic; label: string }[] = [
  { id: "all", label: "All" },
  { id: "leave", label: "Leave" },
  { id: "wfh", label: "WFH" },
  { id: "expenses", label: "Expenses" },
  { id: "attendance", label: "Attendance" },
  { id: "appraisal", label: "Appraisal" },
  { id: "conduct", label: "Conduct" },
];

interface QuickQuery {
  label: string;
  icon: string;
  topic: Topic;
  query: string;
}

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
    "Hello! I'm HRBot for your company. Ask about leave, WFH, expenses, attendance, appraisals, and more. I answer only from your company policy window.",
};

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

function MessageBubble({ message, timestamp }: { message: Message; timestamp: Date }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-2.5 items-start ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex-shrink-0 w-7 h-7 rounded-full border text-[11px] font-medium flex items-center justify-center select-none ${
          isUser
            ? "border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300"
            : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 text-slate-500 dark:text-slate-400"
        }`}
        aria-hidden="true"
      >
        {isUser ? "You" : "HR"}
      </div>

      <div className={`flex flex-col gap-1 max-w-[80%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`px-4 py-3.5 rounded-3xl border shadow-sm text-[14px] leading-7 ${
            isUser
              ? "bg-blue-500 text-white border-blue-500 shadow-blue-500/10"
              : message.error
                ? "bg-rose-50 text-rose-900 border-rose-200 dark:bg-rose-950 dark:text-rose-100 dark:border-rose-800"
                : "bg-slate-50 dark:bg-slate-950 border-slate-200 dark:border-slate-800 text-slate-900 dark:text-slate-100"
          }`}
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

function TailwindChatbot({ token }: { token: string }) {
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

  const filteredQueries = useMemo(() => {
    return QUICK_QUERIES.filter(
      (q) =>
        (activeTopic === "all" || q.topic === activeTopic) &&
        (!search ||
          q.label.toLowerCase().includes(search.toLowerCase()) ||
          q.query.toLowerCase().includes(search.toLowerCase()))
    );
  }, [activeTopic, search]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading || !token) return;

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
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
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
        if (!res.ok) throw new Error(data.detail ?? data.error ?? "Unknown server error");

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
            content: `I couldn't reach the backend at ${BACKEND_URL}.\n\nError: ${msg}`,
            error: true,
          },
        ]);
      } finally {
        setIsLoading(false);
        setTimestamps((prev) => [...prev, new Date()]);
        inputRef.current?.focus();
      }
    },
    [isLoading, messages, token]
  );

  return (
    <div className="grid lg:grid-cols-[272px_1fr] gap-5 items-start">
      <aside className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-5 flex flex-col gap-5">
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

        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-2.5">Topics</p>
          <div className="flex flex-wrap gap-1.5">
            {TOPICS.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTopic(t.id)}
                className={`text-[12px] px-2.5 py-1 rounded-md border transition-colors ${
                  activeTopic === t.id
                    ? "border-slate-400 dark:border-slate-500 bg-slate-900 dark:bg-white text-white dark:text-slate-900"
                    : "border-slate-200 dark:border-slate-800 text-slate-500 dark:text-slate-400 hover:border-slate-300 dark:hover:border-slate-700 hover:text-slate-800 dark:hover:text-slate-200"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="h-px bg-slate-100 dark:bg-slate-800" />

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
                  <span className="text-[11px] text-slate-400 dark:text-slate-600 line-clamp-1">{item.query}</span>
                </button>
              ))
            )}
          </div>
        </div>
      </aside>

      <main className="flex flex-col gap-5 flex-1 min-w-0">
        <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl flex flex-col overflow-hidden">
          <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-slate-400 dark:text-slate-600 mb-1">Chat module</p>
              <h2 className="text-[17px] font-medium">Policy assistant</h2>
            </div>
          </div>

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
              placeholder="Ask a policy question…"
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
  );
}

// ─── Main Employee Dashboard Component ────────────────────────────────────────

export default function EmployeeDashboard() {
  const router = useRouter();
  const [token, setToken] = useState<string>("");
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [profile, setProfile] = useState<EmployeeProfile | null>(null);
  const [leaveBalance, setLeaveBalance] = useState<LeaveBalance | null>(null);
  const [attendance, setAttendance] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const messageEndRef = useRef<HTMLDivElement>(null);
  const [leaveApplication, setLeaveApplication] = useState({ from_date: "", to_date: "", reason: "", leave_type: "casual_leave" });

  // Check auth
  useEffect(() => {
    const storedToken = localStorage.getItem("token");
    const storedEmployee = localStorage.getItem("employee_profile");
    if (!storedToken) {
      router.push("/login");
    } else {
      setToken(storedToken);
      if (storedEmployee) {
        setProfile(JSON.parse(storedEmployee));
      }
      loadEmployeeData(storedToken);
    }
  }, [router]);

  // Load employee data
  const loadEmployeeData = async (authToken: string) => {
    setLoading(true);
    try {
      // Fetch profile
      const profileResponse = await fetch(`${BACKEND_URL}/api/v1/employees/profile/me`, {
        headers: { "Authorization": `Bearer ${authToken}` },
      });

      // Fetch leave balance
      const leaveResponse = await fetch(`${BACKEND_URL}/api/v1/employees/leave-balance/me`, {
        headers: { "Authorization": `Bearer ${authToken}` },
      });

      // Fetch attendance (last 5 days)
      const attendanceResponse = await fetch(`${BACKEND_URL}/api/v1/employees/attendance/me?days=5`, {
        headers: { "Authorization": `Bearer ${authToken}` },
      });

      if (profileResponse.ok) {
        const profileData = await profileResponse.json();
        setProfile(profileData);
      }

      if (leaveResponse.ok) {
        const leaveData = await leaveResponse.json();
        setLeaveBalance({
          casual_leave_remaining: leaveData.casual_leave_remaining,
          sick_leave_remaining: leaveData.sick_leave_remaining,
          privilege_leave_remaining: leaveData.privilege_leave_remaining,
          floating_holidays_remaining: leaveData.floating_holidays_remaining,
        });
      }

      if (attendanceResponse.ok) {
        const attendanceData = await attendanceResponse.json();
        setAttendance(attendanceData);
      }
    } catch (error) {
      console.error("Error loading employee data:", error);
      alert("Error loading data from server. Please refresh the page.");
    } finally {
      setLoading(false);
    }
  };

  // Search policies
  const handlePolicySearch = async () => {
    if (!searchQuery.trim()) return;

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/vectordb/search?query=${encodeURIComponent(searchQuery)}&top_k=5`, {
        headers: { "Authorization": `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.policies || []);
      }
    } catch (error) {
      console.error("Search error:", error);
    }
  };

  // Apply leave
  const handleLeaveApplication = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leaveApplication.from_date || !leaveApplication.to_date) {
      alert("Please select dates");
      return;
    }

    try {
      setMessages([...messages, { role: "user", content: `Applying for ${leaveApplication.leave_type} from ${leaveApplication.from_date} to ${leaveApplication.to_date}` }]);
      
      // Simulate processing
      setTimeout(() => {
        setMessages((prev) => [...prev, { role: "assistant", content: "✓ Leave application submitted successfully! Your manager will review it soon." }]);
      }, 1000);

      setLeaveApplication({ from_date: "", to_date: "", reason: "", leave_type: "casual_leave" });
    } catch (error) {
      console.error("Error applying leave:", error);
    }
  };

  // Chat with HR bot (legacy inline bot)
  const handleChatSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const input = (e.currentTarget as HTMLFormElement).query?.value || "";
    if (!input.trim()) return;

    setMessages([...messages, { role: "user", content: input }]);
    (e.currentTarget as HTMLFormElement).reset();

    try {
      const response = await fetch(`${BACKEND_URL}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ message: input, history: messages }),
      });

      if (response.ok) {
        const data = await response.json();
        setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
      } else {
        setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, I couldn't process that. Please try again.", error: true }]);
      }
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: "Connection error. Please try again.", error: true }]);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("employee_profile");
    router.push("/login");
  };

  const scrollToBottom = () => {
    messageEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  if (!profile) return <div style={{ padding: "20px", textAlign: "center" }}>Loading...</div>;

  return (
    <div style={{ fontFamily: "Arial, sans-serif", backgroundColor: "#f5f5f5", minHeight: "100vh" }}>
      {/* Header */}
      <header style={{ backgroundColor: "#2c3e50", color: "white", padding: "20px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: "24px" }}>Employee Portal</h1>
            <p style={{ margin: "5px 0 0 0", fontSize: "14px", color: "#bdc3c7" }}>{profile.first_name} {profile.last_name}</p>
          </div>
          <button onClick={handleLogout} style={{ backgroundColor: "#e74c3c", color: "white", border: "none", padding: "10px 20px", borderRadius: "4px", cursor: "pointer" }}>
            Logout
          </button>
        </div>
      </header>

      {/* Tabs */}
      <nav style={{ backgroundColor: "white", borderBottom: "2px solid #ecf0f1", padding: "0 20px" }}>
        <div style={{ maxWidth: "1200px", margin: "0 auto", display: "flex", gap: "20px", overflowX: "auto" }}>
          {(["overview", "attendance", "leaves", "profile", "search", "chatbot"] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                padding: "15px 0",
                backgroundColor: "transparent",
                border: "none",
                borderBottom: activeTab === tab ? "3px solid #3498db" : "none",
                color: activeTab === tab ? "#3498db" : "#7f8c8d",
                cursor: "pointer",
                fontSize: "14px",
                fontWeight: activeTab === tab ? "bold" : "normal",
                whiteSpace: "nowrap",
              }}
            >
              {TAB_LABELS[tab]}
            </button>
          ))}
        </div>
      </nav>

      {/* Content */}
      <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "20px" }}>
        {/* Overview Tab */}
        {activeTab === "overview" && leaveBalance && (
          <div>
            <h2 style={{ marginTop: 0 }}>Welcome, {profile.first_name}!</h2>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "20px", marginBottom: "30px" }}>
              <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginBottom: "8px" }}>Department</div>
                <div style={{ fontSize: "16px", fontWeight: "bold" }}>{profile.department}</div>
              </div>

              <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginBottom: "8px" }}>Designation</div>
                <div style={{ fontSize: "16px", fontWeight: "bold" }}>{profile.designation}</div>
              </div>

              <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginBottom: "8px" }}>Manager</div>
                <div style={{ fontSize: "16px", fontWeight: "bold" }}>{profile.manager_name}</div>
              </div>

              <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginBottom: "8px" }}>Performance Rating</div>
                <div style={{ fontSize: "16px", fontWeight: "bold", color: "#27ae60" }}>{profile.performance_rating}/5.0 ⭐</div>
              </div>
            </div>

            <h3>Leave Balance</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "15px" }}>
              <div style={{ backgroundColor: "white", padding: "15px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)", textAlign: "center" }}>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#3498db" }}>{leaveBalance.casual_leave_remaining}</div>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginTop: "5px" }}>Casual Leave</div>
              </div>

              <div style={{ backgroundColor: "white", padding: "15px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)", textAlign: "center" }}>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#e74c3c" }}>{leaveBalance.sick_leave_remaining}</div>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginTop: "5px" }}>Sick Leave</div>
              </div>

              <div style={{ backgroundColor: "white", padding: "15px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)", textAlign: "center" }}>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#f39c12" }}>{leaveBalance.privilege_leave_remaining}</div>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginTop: "5px" }}>Privilege Leave</div>
              </div>

              <div style={{ backgroundColor: "white", padding: "15px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)", textAlign: "center" }}>
                <div style={{ fontSize: "24px", fontWeight: "bold", color: "#27ae60" }}>{leaveBalance.floating_holidays_remaining}</div>
                <div style={{ fontSize: "12px", color: "#7f8c8d", marginTop: "5px" }}>Floating Holidays</div>
              </div>
            </div>
          </div>
        )}

        {/* Attendance Tab */}
        {activeTab === "attendance" && (
          <div>
            <h2 style={{ marginTop: 0 }}>Attendance History</h2>
            <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #ecf0f1" }}>
                    <th style={{ textAlign: "left", padding: "10px", fontWeight: "bold" }}>Date</th>
                    <th style={{ textAlign: "left", padding: "10px", fontWeight: "bold" }}>Status</th>
                    <th style={{ textAlign: "left", padding: "10px", fontWeight: "bold" }}>Hours Worked</th>
                  </tr>
                </thead>
                <tbody>
                  {attendance.map((record, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #ecf0f1" }}>
                      <td style={{ padding: "10px" }}>{record.date}</td>
                      <td style={{ padding: "10px" }}>
                        <span style={{
                          padding: "4px 8px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          backgroundColor: record.status === "Present" ? "#d5f4e6" : record.status === "WFH" ? "#d6eaf8" : "#fadbd8",
                          color: record.status === "Present" ? "#27ae60" : record.status === "WFH" ? "#3498db" : "#e74c3c"
                        }}>
                          {record.status}
                        </span>
                      </td>
                      <td style={{ padding: "10px" }}>{record.hours_worked}h</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Leaves Tab */}
        {activeTab === "leaves" && (
          <div>
            <h2 style={{ marginTop: 0 }}>Apply for Leave</h2>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
              <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
                <h3 style={{ marginTop: 0 }}>New Application</h3>
                <form onSubmit={handleLeaveApplication}>
                  <div style={{ marginBottom: "15px" }}>
                    <label style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>Leave Type:</label>
                    <select value={leaveApplication.leave_type} onChange={(e) => setLeaveApplication({ ...leaveApplication, leave_type: e.target.value })} style={{ width: "100%", padding: "10px", border: "1px solid #bdc3c7", borderRadius: "4px", boxSizing: "border-box" }}>
                      <option value="casual_leave">Casual Leave</option>
                      <option value="sick_leave">Sick Leave</option>
                      <option value="privilege_leave">Privilege Leave</option>
                    </select>
                  </div>

                  <div style={{ marginBottom: "15px" }}>
                    <label style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>From Date:</label>
                    <input type="date" value={leaveApplication.from_date} onChange={(e) => setLeaveApplication({ ...leaveApplication, from_date: e.target.value })} style={{ width: "100%", padding: "10px", border: "1px solid #bdc3c7", borderRadius: "4px", boxSizing: "border-box" }} />
                  </div>

                  <div style={{ marginBottom: "15px" }}>
                    <label style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>To Date:</label>
                    <input type="date" value={leaveApplication.to_date} onChange={(e) => setLeaveApplication({ ...leaveApplication, to_date: e.target.value })} style={{ width: "100%", padding: "10px", border: "1px solid #bdc3c7", borderRadius: "4px", boxSizing: "border-box" }} />
                  </div>

                  <div style={{ marginBottom: "15px" }}>
                    <label style={{ display: "block", marginBottom: "5px", fontWeight: "bold" }}>Reason:</label>
                    <textarea value={leaveApplication.reason} onChange={(e) => setLeaveApplication({ ...leaveApplication, reason: e.target.value })} style={{ width: "100%", padding: "10px", border: "1px solid #bdc3c7", borderRadius: "4px", boxSizing: "border-box", minHeight: "80px" }} placeholder="Reason for leave" />
                  </div>

                  <button type="submit" style={{ backgroundColor: "#27ae60", color: "white", border: "none", padding: "10px 20px", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}>
                    Submit Application
                  </button>
                </form>
              </div>

              <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
                <h3 style={{ marginTop: 0 }}>Chat with HR Bot</h3>
                <div style={{ backgroundColor: "#f8f9fa", borderRadius: "4px", padding: "15px", minHeight: "300px", maxHeight: "400px", overflowY: "auto", marginBottom: "15px" }}>
                  {messages.length === 0 ? (
                    <p style={{ color: "#7f8c8d", textAlign: "center", margin: "50px 0" }}>Ask me about leave policies, attendance, or HR processes</p>
                  ) : (
                    messages.map((msg, i) => (
                      <div key={i} style={{ marginBottom: "10px", textAlign: msg.role === "user" ? "right" : "left" }}>
                        <div style={{
                          display: "inline-block",
                          padding: "10px 15px",
                          borderRadius: "8px",
                          backgroundColor: msg.role === "user" ? "#3498db" : msg.error ? "#e74c3c" : "#ecf0f1",
                          color: msg.role === "user" ? "white" : msg.error ? "white" : "#2c3e50",
                          maxWidth: "80%"
                        }}>
                          {msg.content}
                        </div>
                      </div>
                    ))
                  )}
                  <div ref={messageEndRef} />
                </div>

                <form onSubmit={handleChatSubmit} style={{ display: "flex", gap: "10px" }}>
                  <input type="text" name="query" placeholder="Ask HR..." style={{ flex: 1, padding: "10px", border: "1px solid #bdc3c7", borderRadius: "4px" }} />
                  <button type="submit" style={{ backgroundColor: "#3498db", color: "white", border: "none", padding: "10px 20px", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}>
                    Send
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Profile Tab */}
        {activeTab === "profile" && profile && (
          <div>
            <h2 style={{ marginTop: 0 }}>My Profile</h2>
            <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)" }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
                <div>
                  <p><strong>Employee ID:</strong> {profile.employee_id}</p>
                  <p><strong>Name:</strong> {profile.first_name} {profile.last_name}</p>
                  <p><strong>Email:</strong> {profile.email}</p>
                  <p><strong>Phone:</strong> {profile.phone || "Not provided"}</p>
                </div>

                <div>
                  <p><strong>Department:</strong> {profile.department}</p>
                  <p><strong>Designation:</strong> {profile.designation}</p>
                  <p><strong>Manager:</strong> {profile.manager_name}</p>
                  <p><strong>Office:</strong> {profile.office_location}</p>
                </div>

                <div>
                  <p><strong>Work Mode:</strong> {profile.work_mode}</p>
                  <p><strong>Years with Company:</strong> {profile.years_with_company}</p>
                  <p><strong>Performance Rating:</strong> {profile.performance_rating}/5.0 ⭐</p>
                  <p><strong>Joined:</strong> {profile.date_of_joining || "Not available"}</p>
                </div>

                <div>
                  <p><strong>Skills:</strong> {profile.skills?.length ? profile.skills.join(", ") : "Not specified"}</p>
                  <p><strong>Certifications:</strong> {profile.certifications?.length ? profile.certifications.join(", ") : "None"}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Search Tab */}
        {activeTab === "search" && (
          <div>
            <h2 style={{ marginTop: 0 }}>Search Policies</h2>
            <div style={{ backgroundColor: "white", padding: "20px", borderRadius: "8px", boxShadow: "0 2px 4px rgba(0,0,0,0.1)", marginBottom: "20px" }}>
              <form onSubmit={(e) => { e.preventDefault(); handlePolicySearch(); }} style={{ display: "flex", gap: "10px", marginBottom: "15px" }}>
                <input type="text" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} placeholder="Search policies (e.g., casual leave, work from home)..." style={{ flex: 1, padding: "10px", border: "1px solid #bdc3c7", borderRadius: "4px" }} />
                <button type="submit" style={{ backgroundColor: "#3498db", color: "white", border: "none", padding: "10px 20px", borderRadius: "4px", cursor: "pointer", fontWeight: "bold" }}>
                  Search
                </button>
              </form>

              {searchResults.length > 0 && (
                <div>
                  <h3>Results ({searchResults.length})</h3>
                  {searchResults.map((result, i) => (
                    <div key={i} style={{ backgroundColor: "#f8f9fa", padding: "15px", borderRadius: "4px", marginBottom: "10px", borderLeft: "4px solid #3498db" }}>
                      <p style={{ margin: "0 0 5px 0", fontWeight: "bold" }}>{result.metadata?.section || "Policy"}</p>
                      <p style={{ margin: "0 0 5px 0", color: "#7f8c8d", fontSize: "12px" }}>Match: {(result.score * 100).toFixed(0)}%</p>
                      <p style={{ margin: 0, color: "#2c3e50" }}>{result.metadata?.content_preview || result.content || "Lorem ipsum dolor sit amet..."}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Chatbot Tab */}
        {activeTab === "chatbot" && (
          <div>
            <h2 style={{ marginTop: 0 }}>AI Policy Assist</h2>
            <TailwindChatbot token={token} />
          </div>
        )}
      </main>
    </div>
  );
}
