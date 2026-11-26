import { ChatWindow, Composer, Launcher as LauncherButton, MessageBubble } from "@studio/ui";
import { type KeyboardEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { type CallMode, type CallSession, joinCall } from "./call";
import {
  type Boot,
  type Citation,
  ChatError,
  type Feedback,
  type Launcher,
  NO_LONGER_AVAILABLE,
  type Rating,
  type Resumed,
  ask,
  endCall,
  endConversation,
  interruptCall,
  resume,
  startCall,
  startConversation,
} from "./chat";
import { LAYOUT_MESSAGE, type Layout } from "./embed";
import { FeedbackControls } from "./Feedback";
import { RatingPrompt, UNRATED } from "./Rating";
import { tokenStore } from "./storage";

type Message = {
  role: "visitor" | "agent";
  text: string;
  citations: Citation[];
  /** The Message's id, once the API has it (a reply's when it has finished streaming). */
  id?: string;
  feedback: Feedback | null;
  // The input Guardrail blocked the Visitor's message: the text is the Agent's refusal.
  refused?: boolean;
  // The Agent is searching its knowledge base for this reply (shown until its text streams).
  searching?: boolean;
  // Said in a Call rather than typed: a Spoken Message.
  spoken?: boolean;
};

/**
 * - `loading`: checking a kept Conversation token, to resume its Conversation.
 * - `chat`: the chat (for an Agent that takes Calls, first a choice of Message or Call).
 * - `call`: a Call, over the Conversation log.
 * - `ending`: the Visitor chose "End chat" without having rated it, so they are asked to first.
 * - `ended`: the Visitor ended the chat.
 * - `retired`: the Agent is archived or no longer live.
 */
type Phase = "loading" | "chat" | "call" | "ending" | "ended" | "retired";

const GENERIC = "Something went wrong. Please try again.";

const MINUTE_MS = 60_000;

/** Why the widget returned to the chat when the Agent couldn't answer in a Call. */
export const CALL_UNAVAILABLE = "The assistant can't answer right now. You can still send a message.";

/** Why the widget returned to the chat when a Call reached the Maximum Call length. */
export function callLengthReached(minutes: number): string {
  return `The Call reached its ${String(minutes)}-minute limit. You can still send a message.`;
}

/** Announced, politely, once a Call has connected. */
export const CALL_STARTED = "Call started.";
/** Announced, politely, when a Call ends: with the reason, when it ended for one. */
export const CALL_ENDED = "Call ended.";

/** What a Call view says the Call is doing. */
function callState(mode: CallMode | "connecting", muted: boolean, name: string): string {
  if (mode === "connecting") return "Connecting your call…";
  if (mode === "speaking") return `${name} is speaking…`;
  return muted ? "You're muted." : "Listening…";
}

/** The Conversation's Messages as the log shows them, from the API. */
function logged(resumed: Resumed): Message[] {
  return resumed.messages.map((m) => ({
    role: m.role === "user" ? "visitor" : "agent",
    text: m.content,
    citations: m.citations,
    id: m.id,
    feedback: m.feedback,
    spoken: m.spoken,
  }));
}

/** The built-in searching status, unless the Agent's UI text overrides it. */
export const SEARCHING = "Searching the knowledge base…";

/** What Tab can reach inside the open chat. */
const FOCUSABLE = 'button:not([disabled]), input:not([disabled]), summary, a[href], [tabindex]:not([tabindex="-1"])';

/**
 * Keeps Tab inside `panel` while the bubble is open: past the last control focus wraps to the
 * first, and Shift+Tab before the first wraps to the last.
 */
function trapFocus(event: KeyboardEvent<HTMLElement>) {
  if (event.key !== "Tab") return;
  const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>(FOCUSABLE)];
  const first = focusable[0];
  const last = focusable.at(-1);
  const active = document.activeElement;
  if (event.shiftKey ? active === first : active === last) {
    event.preventDefault();
    ((event.shiftKey ? last : first) as HTMLElement).focus();
  }
}

function message(failure: unknown): string {
  return failure instanceof ChatError ? failure.message : GENERIC;
}

/** The host page's origin, from the frame's address, if it is one; layout goes only there. */
export function hostOrigin(host: string | null): string | null {
  if (!host) return null;
  try {
    const url = new URL(host);
    return /^https?:$/.test(url.protocol) && url.origin === host ? host : null;
  } catch {
    return null;
  }
}

/** An answer's sources; each expands to the passage it cited, when the widget was sent one. */
function Sources({ citations }: { citations: Citation[] }) {
  return (
    <div className="sources">
      Sources:{" "}
      {citations.map((citation, index) => {
        const name = citation.document_name ?? citation.label;
        return (
          <span key={index}>
            {index > 0 && ", "}
            {citation.passage === undefined ? (
              name
            ) : (
              <details>
                <summary>{name}</summary>
                <blockquote>{citation.passage}</blockquote>
              </details>
            )}
          </span>
        );
      })}
    </div>
  );
}

/**
 * The chat a Visitor sees inside the iframe, in the Organisation's Theme: the Agent's greeting
 * and starter questions, their questions and the Agent's streamed replies with expandable
 * sources. As a bubble it opens from a Launcher in the corner; inline it is always open. It
 * tells the host page (`host`, the only origin it posts to) how to size its frame. The
 * Conversation token is kept in the iframe's storage, so a Visitor who comes back resumes their
 * Conversation; they can start a new chat or end it.
 *
 * For an Agent that takes Calls, the Visitor moves between typing and talking in one
 * Conversation: the header's Call button starts a Call, and End call returns to the chat. A
 * reload or page change ends the Call; the resumed Conversation offers "Continue call", which
 * starts a new Call only when tapped.
 */
export function Widget({ boot, launcher, host = null }: { boot: Boot; launcher?: Launcher | null; host?: string | null }) {
  const type = launcher ?? boot.theme.launcher_type;
  const bubble = type === "bubble";
  const [open, setOpen] = useState(!bubble);
  const store = useMemo(() => tokenStore(boot.agent), [boot.agent]);
  const [phase, setPhase] = useState<Phase>(() => (store.load() ? "loading" : "chat"));
  const [messages, setMessages] = useState<Message[]>([]);
  // The Conversation Rating, and whether the Visitor dismissed the rating prompt.
  const [rating, setRating] = useState<Rating>(UNRATED);
  const [pending, setPending] = useState(false);
  const [error, setErrorText] = useState<string | null>(null);
  // Why a Call ended is announced politely, so its note isn't an alert as well.
  const [quietError, setQuietError] = useState(false);
  // The last completed reply, for screen readers; its `id` makes a repeated reply a new node.
  const [announcement, setAnnouncement] = useState<{ id: number; text: string } | null>(null);
  // The Conversation token, once the bootstrap token has been exchanged for one (or kept from
  // an earlier page load).
  const token = useRef<string | null>(null);
  // For an Agent that takes Calls: whether the Visitor has chosen Message or Call yet.
  const [chosen, setChosen] = useState(false);
  // The Call being held: what it is doing, and whether the Visitor muted it.
  const [callMode, setCallMode] = useState<CallMode | "connecting">("connecting");
  const [muted, setMuted] = useState(false);
  // A resumed Conversation whose Call the page cut off: the Visitor is offered "Continue call".
  const [continuing, setContinuing] = useState(false);
  const call = useRef<CallSession | null>(null);
  // Whether the Call being held has connected (its start was announced).
  const connected = useRef(false);
  // Leaves and ends the Call being held, when the widget leaves the page during it.
  const leaveCall = useRef<(() => void) | null>(null);
  // Ends the Call when it reaches the Maximum Call length, as the platform does.
  const callLimit = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const root = useRef<HTMLDivElement | null>(null);
  const opened = useRef(false);
  const focusInput = useRef(false);

  function messageBox() {
    return root.current?.querySelector<HTMLInputElement>('input[name="message"], .choice button');
  }

  // Whether the widget is still on the page: a Call that finishes starting after it left is
  // ended, not joined.
  const mounted = useRef(true);
  // A Call doesn't outlive the widget: leaving the page (a reload, a page change, or the widget
  // going away) leaves the voice session, ends the Call and stops its limit timer. The kept
  // Call mark stays, so the next page offers "Continue call".
  useEffect(() => {
    mounted.current = true;
    function leavePage() {
      clearTimeout(callLimit.current);
      const leaving = leaveCall.current;
      leaveCall.current = null;
      leaving?.();
    }
    window.addEventListener("pagehide", leavePage);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", leavePage);
      leavePage();
    };
  }, []);

  useEffect(() => {
    const target = hostOrigin(host);
    if (target && window.parent !== window) {
      const layout: Layout & { type: string } = { type: LAYOUT_MESSAGE, launcher: type, open, position: boot.theme.launcher_position };
      window.parent.postMessage(layout, target);
    }
    // Opening moves focus into the chat; closing returns it to the Launcher.
    if (!bubble) return;
    if (open) messageBox()?.focus();
    else if (opened.current) root.current?.querySelector<HTMLButtonElement>(".launcher button")?.focus();
    opened.current ||= open;
  }, [open, type, bubble, host, boot.theme.launcher_position]);

  function setError(text: string | null, quiet = false) {
    setErrorText(text);
    setQuietError(quiet);
  }

  /** Says `text` politely to screen readers (a repeated text is a new node, so it is said again). */
  function announce(text: string) {
    setAnnouncement((last) => ({ id: (last?.id ?? 0) + 1, text }));
  }

  function forget() {
    token.current = null;
    store.clear();
  }

  function retire() {
    forget();
    setPhase("retired");
  }

  // A Visitor coming back within 24 hours gets their Conversation back.
  useEffect(() => {
    const kept = store.load();
    if (!kept) return;
    // Nothing to cancel on unmount: the widget is the iframe's whole page.
    void resume(boot, kept).then(
      (resumed) => {
        if (resumed === null) {
          store.clear();
        } else {
          token.current = kept;
          setRating(resumed.rating);
          setMessages(logged(resumed));
          // A Call cut off by the page going away: a still-open one ends now, and the Visitor
          // can start a new one.
          if (resumed.call_open) void endCall(boot, kept);
          setContinuing(resumed.call_open || store.inCall());
        }
        setPhase("chat");
      },
      (failure: unknown) => {
        if (failure instanceof ChatError && failure.status === 404) {
          store.clear();
          setPhase("retired");
          return;
        }
        // Keep the token: the Conversation can carry on even if its history didn't load.
        token.current = kept;
        setError(message(failure));
        setPhase("chat");
      },
    );
  }, [boot, store]);

  // The control that started a Call goes away, so focus moves to the Call view.
  useEffect(() => {
    if (phase === "call") root.current?.querySelector<HTMLElement>(".call")?.focus();
  }, [phase]);

  useEffect(() => {
    if (focusInput.current && phase === "chat") {
      focusInput.current = false;
      messageBox()?.focus();
    }
  });

  // The newest Message scrolls into view as it arrives, without animation for Visitors who
  // prefer reduced motion.
  useEffect(() => {
    const newest = root.current?.querySelector("li[data-from]:last-of-type");
    if (!newest || messages.length === 0) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    newest.scrollIntoView({ block: "end", behavior: reduce ? "auto" : "smooth" });
  }, [messages]);

  function updateReply(update: (reply: Message) => Message) {
    setMessages((current) => [...current.slice(0, -1), update(current[current.length - 1] as Message)]);
  }

  async function send(question: string) {
    setError(null);
    setPending(true);
    // Typing instead: the cut-off Call is no longer offered.
    setContinuing(false);
    store.saveCall(false);
    setMessages((current) => [
      ...current,
      { role: "visitor", text: question, citations: [], feedback: null },
      { role: "agent", text: "", citations: [], feedback: null },
    ]);
    try {
      if (token.current === null) {
        token.current = await startConversation(boot);
        store.save(token.current);
      }
      let answer = "";
      let searched = false;
      const id = await ask(boot, token.current, question, {
        onSearch: () => {
          updateReply((reply) => ({ ...reply, searching: true }));
          // Announced once per reply, however many Searches it makes.
          if (searched) return;
          searched = true;
          announce(boot.ui_text.searching_status ?? SEARCHING);
        },
        onToken: (text) => {
          answer += text;
          updateReply((reply) => ({ ...reply, text: reply.text + text }));
        },
        onReplace: (text) => {
          answer = text;
          updateReply((reply) => ({ ...reply, text }));
        },
        onRetract: () => {
          // The Agent went on to search: what streamed wasn't the answer. It is cleared and
          // never announced; the searching status shows until the answer streams.
          answer = "";
          updateReply((reply) => ({ ...reply, text: "", searching: true }));
        },
        onRefusal: (text) => {
          updateReply((reply) => ({ ...reply, text, refused: true }));
        },
        onCitation: (citation) => {
          updateReply((reply) => ({ ...reply, citations: [...reply.citations, citation] }));
        },
      });
      updateReply((reply) => ({ ...reply, id }));
      announce(`${boot.name}: ${answer}`);
    } catch (failure) {
      if (failure instanceof ChatError && failure.status === 404) {
        retire();
        return;
      }
      // An expired or ended token: the next question starts a new Conversation.
      if (failure instanceof ChatError && failure.status === 401) forget();
      // Drop the reply and whatever of it streamed before the failure.
      setMessages((current) => current.slice(0, -1));
      const unavailable = failure instanceof ChatError && failure.unavailable ? boot.ui_text.unavailable_message : null;
      setError(unavailable ?? message(failure));
    } finally {
      setPending(false);
    }
  }

  /** Fills the log from the API: the Spoken Messages, each reply with its sources and Message ID. */
  async function refreshLog() {
    const resumed = token.current === null ? null : await resume(boot, token.current).catch(() => null);
    if (resumed) setMessages(logged(resumed));
  }

  /**
   * After a spoken reply: the log from the API. An Agent that couldn't answer has spoken its
   * Unavailable text and ended the Call, so the Visitor returns to messaging; a retired one is
   * shown retired.
   */
  async function replied(conversation: string) {
    let resumed: Resumed | null;
    try {
      resumed = await resume(boot, conversation);
    } catch (failure) {
      if (failure instanceof ChatError && failure.status === 404) {
        leave();
        retire();
      }
      return;
    }
    // The Visitor ended the Call while its log was read back.
    if (call.current === null) return;
    if (resumed) setMessages(logged(resumed));
    if (!resumed?.call_open) await hangUp(boot.ui_text.unavailable_message ?? CALL_UNAVAILABLE);
  }

  /** Leaves the Call being held, without ending it. */
  function leave() {
    clearTimeout(callLimit.current);
    leaveCall.current = null;
    call.current?.end();
    call.current = null;
    store.saveCall(false);
  }

  /** New chat or End chat during a Call: leaves the Call and ends it. */
  function stopCall() {
    if (phase !== "call") return;
    leave();
    announce(CALL_ENDED);
    // A Call past connecting has its Conversation token.
    void endCall(boot, token.current as string);
  }

  /**
   * Leaves the Call, ends it, and returns to the chat with what was said in the log. Its end, and
   * why it ended (`failure`), are announced politely; a Call that never connected announces only why.
   */
  async function hangUp(failure: string | null = null) {
    leave();
    if (token.current !== null) await endCall(boot, token.current);
    await refreshLog();
    setError(failure, true);
    announce([connected.current ? CALL_ENDED : null, failure].filter((part) => part !== null).join(" "));
    connected.current = false;
    focusInput.current = true;
    setPhase("chat");
  }

  async function startTalking() {
    setChosen(true);
    setContinuing(false);
    setError(null);
    setMuted(false);
    setCallMode("connecting");
    connected.current = false;
    setPhase("call");
    try {
      if (token.current === null) {
        token.current = await startConversation(boot);
        store.save(token.current);
      }
      const started = await startCall(boot, token.current);
      if (!mounted.current) {
        await endCall(boot, token.current);
        return;
      }
      const conversation = token.current;
      const session = joinCall(boot, started, {
        onMode: (mode) => {
          setCallMode(mode);
          if (connected.current) return;
          connected.current = true;
          announce(CALL_STARTED);
        },
        // Best effort: the reply being spoken is marked interrupted.
        onInterruption: () => void interruptCall(boot, conversation),
        onVisitorWords: (words) => {
          setMessages((current) => [...current, { role: "visitor", text: words, citations: [], feedback: null, spoken: true }]);
        },
        onReply: () => void replied(conversation),
        onFailure: (failure) => void hangUp(failure.message),
      });
      call.current = session;
      store.saveCall(true);
      leaveCall.current = () => {
        session.end();
        void endCall(boot, conversation);
      };
      callLimit.current = setTimeout(() => void hangUp(callLengthReached(started.max_call_minutes)), started.max_call_minutes * MINUTE_MS);
    } catch (failure) {
      if (failure instanceof ChatError && failure.status === 404) {
        retire();
        return;
      }
      if (failure instanceof ChatError && failure.status === 401) forget();
      const unavailable = failure instanceof ChatError && failure.unavailable ? boot.ui_text.unavailable_message : null;
      // The Call never started: back to the chat, where the Visitor can still type.
      await hangUp(unavailable ?? message(failure));
    }
  }

  function onSend(text: string) {
    const question = text.trim();
    if (question) void send(question);
  }

  /** Ends the current Conversation (if one started) and clears the chat. */
  function close(next: Phase) {
    if (token.current !== null) void endConversation(boot, token.current);
    forget();
    setContinuing(false);
    setMessages([]);
    setRating(UNRATED);
    setError(null);
    focusInput.current = next === "chat";
    setPhase(next);
  }

  // The Agent's finished replies, which the rating prompt counts.
  const replies = messages.filter((m) => m.role === "agent" && m.id !== undefined).length;

  /** "End chat": a Visitor who hasn't rated a Conversation with a reply is asked to first. */
  function endChat() {
    stopCall();
    if (token.current !== null && replies > 0 && rating.score === null) setPhase("ending");
    else close("ended");
  }

  const ratingPrompt = (ending: boolean) => (
    <RatingPrompt
      boot={boot}
      token={() => token.current}
      rating={rating}
      replies={replies}
      ending={ending}
      onChange={setRating}
      onEnd={() => {
        close("ended");
      }}
      onKeepChatting={() => {
        focusInput.current = true;
        setPhase("chat");
      }}
    />
  );

  const name = boot.name;
  // An Agent that takes Calls opens on a choice of Message or Call.
  const choosing = boot.calls && phase === "chat" && !chosen && messages.length === 0;
  const chatting = phase === "chat" && !choosing;
  // While the Visitor is asked to rate on "End chat", and during a Call, the Conversation stays in view.
  const showing = chatting || phase === "ending" || phase === "call";
  // New chat and End chat stay in the header during a Call, and end it; not while it connects.
  const connecting = phase === "call" && callMode === "connecting";
  let footer: ReactNode;
  if (phase === "retired") {
    footer = (
      <p role="status" className="notice">
        {NO_LONGER_AVAILABLE}
      </p>
    );
  } else if (phase === "loading") {
    footer = (
      <p role="status" className="notice">
        Loading your chat…
      </p>
    );
  } else if (phase === "ending") {
    footer = ratingPrompt(true);
  } else if (choosing) {
    footer = (
      <div className="choice" role="group" aria-labelledby="choice-prompt">
        <p id="choice-prompt">How would you like to ask?</p>
        <div className="choice-buttons">
          <button
            type="button"
            onClick={() => {
              setChosen(true);
              focusInput.current = true;
            }}
          >
            {boot.ui_text.message_choice ?? "Message"}
          </button>
          <button type="button" onClick={() => void startTalking()}>
            {boot.ui_text.call_choice ?? "Call"}
          </button>
        </div>
      </div>
    );
  } else if (phase === "call") {
    footer = (
      <div className="call" role="group" aria-label="Call" tabIndex={-1}>
        {/* Shown, not read out: a screen reader saying "speaking" would talk over the Agent. */}
        <p role="status" aria-live="off" className="call-state" data-mode={callMode}>
          {callState(callMode, muted, name)}
        </p>
        <div className="call-controls">
          <button
            type="button"
            aria-pressed={muted}
            disabled={callMode === "connecting"}
            onClick={() => {
              call.current?.setMuted(!muted);
              setMuted(!muted);
            }}
          >
            Mute
          </button>
          <button type="button" className="end-call" disabled={callMode === "connecting"} onClick={() => void hangUp()}>
            End call
          </button>
        </div>
      </div>
    );
  } else if (phase === "ended") {
    footer = (
      <div className="notice ended">
        <p role="status">You ended the chat.</p>
        <button
          type="button"
          onClick={() => {
            focusInput.current = true;
            setPhase("chat");
          }}
        >
          Start a new chat
        </button>
      </div>
    );
  } else {
    footer = (
      <>
        {error && (
          <p role={quietError ? undefined : "alert"} className="error">
            {error}
          </p>
        )}
        {messages.length === 0 && boot.starter_questions.length > 0 && (
          <ul aria-label="Suggested questions" className="starters">
            {boot.starter_questions.map((question) => (
              <li key={question}>
                <button
                  type="button"
                  onClick={() => {
                    onSend(question);
                  }}
                >
                  {question}
                </button>
              </li>
            ))}
          </ul>
        )}
        {continuing && (
          <p className="continue-call">
            <button type="button" onClick={() => void startTalking()}>
              Continue call
            </button>
          </p>
        )}
        {ratingPrompt(false)}
        <Composer onSend={onSend} disabled={pending} sendLabel={pending ? "Answering…" : (boot.ui_text.send_button ?? "Send")} />
      </>
    );
  }

  return (
    <div
      ref={root}
      className="widget"
      data-launcher={type}
      data-open={open}
      data-position={boot.theme.launcher_position}
      onKeyDown={(event) => {
        if (bubble && event.key === "Escape") setOpen(false);
      }}
    >
      {open && (
        <div className="panel" {...(bubble ? { onKeyDown: trapFocus } : {})}>
          <ChatWindow
            className="chat"
            agentName={name}
            logoUrl={boot.logo_url}
            avatarUrl={boot.avatar_url}
            {...(showing ? { logLabel: "Conversation" } : {})}
            // Already on the page at the choice, so a Call's start is announced.
            {...(showing || choosing ? { announcements: announcement && <p key={announcement.id}>{announcement.text}</p> } : {})}
            actions={
              <>
                {(chatting || phase === "call") && (
                  <span className="controls">
                    {boot.calls && chatting && (
                      <button type="button" disabled={pending} onClick={() => void startTalking()}>
                        Call
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={pending || connecting}
                      onClick={() => {
                        stopCall();
                        close("chat");
                      }}
                    >
                      New chat
                    </button>
                    <button type="button" disabled={pending || connecting} onClick={endChat}>
                      End chat
                    </button>
                  </span>
                )}
                {bubble && (
                  <button
                    type="button"
                    className="close"
                    aria-label="Close chat"
                    onClick={() => {
                      setOpen(false);
                    }}
                  >
                    ×
                  </button>
                )}
              </>
            }
            composer={footer}
          >
            {showing && boot.greeting && (
              <MessageBubble from="agent" label={`${name}'s greeting`}>
                {boot.greeting}
              </MessageBubble>
            )}
            {showing &&
              messages.map((message, index) => (
                <MessageBubble
                  key={index}
                  from={message.role}
                  label={message.role === "visitor" ? "You" : name}
                  {...(message.refused ? { className: "refusal" } : {})}
                >
                  {message.searching && !message.text ? <p className="searching">{boot.ui_text.searching_status ?? SEARCHING}</p> : <p>{message.text}</p>}
                  {boot.citations && message.citations.length > 0 && <Sources citations={message.citations} />}
                  {message.role === "agent" && message.id !== undefined && (
                    <FeedbackControls
                      boot={boot}
                      token={() => token.current}
                      messageId={message.id}
                      feedback={message.feedback}
                      onChange={(feedback) => {
                        setMessages((current) => current.map((m, i) => (i === index ? { ...m, feedback } : m)));
                      }}
                    />
                  )}
                </MessageBubble>
              ))}
          </ChatWindow>
        </div>
      )}
      {bubble && (
        <span className="launcher">
          <LauncherButton
            open={open}
            position={boot.theme.launcher_position}
            onToggle={() => {
              setOpen((current) => !current);
            }}
          />
        </span>
      )}
    </div>
  );
}
