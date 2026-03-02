"use client";

import { type ReactNode, useState } from "react";
import { Check } from "lucide-react";

export function Section(props: { title: string; children: ReactNode }) {
  return (
    <div
      className="rounded-2xl border p-6"
      style={{
        borderColor: "rgba(255,255,255,0.08)",
        backgroundColor: "rgba(24, 24, 27, 0.35)",
      }}
    >
      <div className="text-sm font-semibold">{props.title}</div>
      <div className="mt-4">{props.children}</div>
    </div>
  );
}

export function TabButton(props: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      className="btn-press rounded-xl px-3 py-1.5 text-xs font-semibold transition-colors hover:bg-white/10"
      style={{
        backgroundColor: props.active ? "rgba(99, 102, 241, 0.15)" : undefined,
        border: "1px solid rgba(255,255,255,0.08)",
        color: props.active ? "rgba(255,255,255,0.95)" : "rgba(255,255,255,0.70)",
      }}
    >
      {props.children}
    </button>
  );
}

export function ActionButton(props: {
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={props.onClick}
      disabled={props.disabled}
      className="btn-press rounded-xl px-4 py-2 text-sm font-medium disabled:opacity-50 transition-colors hover:bg-white/5"
      style={{
        backgroundColor: "rgba(99, 102, 241, 0.15)",
        border: "1px solid rgba(99, 102, 241, 0.35)",
      }}
    >
      {props.children}
    </button>
  );
}

export function StatCard(props: {
  label: string;
  value: string;
  description: string;
  statusColor?: string;
}) {
  return (
    <div
      className="rounded-2xl border px-4 py-3"
      style={{
        borderColor: "rgba(255,255,255,0.08)",
        backgroundColor: "rgba(24, 24, 27, 0.25)",
      }}
    >
      <div
        className="text-[11px] font-semibold uppercase tracking-widest"
        style={{ color: "#71717a" }}
      >
        {props.label}
      </div>
      <div
        className="mt-2 text-xl font-semibold tracking-tight"
        style={{ color: props.statusColor ?? "rgba(230,233,242,0.95)" }}
      >
        {props.value}
      </div>
      <div
        className="mt-2 text-[11px] leading-relaxed"
        style={{ color: "rgba(138,144,178,0.7)" }}
      >
        {props.description}
      </div>
    </div>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const color = statusColor(status);
  const bg = statusBg(status);
  return (
    <span
      className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
      style={{ color, backgroundColor: bg }}
    >
      {formatStatus(status)}
    </span>
  );
}

export function SourceCard(props: {
  icon: ReactNode;
  title: string;
  weight: string;
  description: string;
  completed: boolean;
  actionLabel: string;
  onAction?: () => void;
  href?: string;
  note?: string;
  disabled?: boolean;
}) {
  return (
    <div
      className="rounded-2xl border p-5 h-full flex flex-col"
      style={{
        borderColor: props.completed ? "rgba(34, 197, 94, 0.2)" : "rgba(255,255,255,0.08)",
        backgroundColor: props.completed ? "rgba(34, 197, 94, 0.04)" : "rgba(24, 24, 27, 0.35)",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span style={{ color: "rgba(138, 92, 255, 0.9)" }}>{props.icon}</span>
          <span
            className="text-sm font-semibold"
            style={{ color: "rgba(230,233,242,0.95)" }}
          >
            {props.title}
          </span>
        </div>
        <span
          className="rounded-full px-2 py-0.5 text-[10px] font-bold"
          style={{
            backgroundColor: "rgba(99, 102, 241, 0.12)",
            color: "rgba(165, 180, 252, 1)",
          }}
        >
          {props.weight}
        </span>
      </div>

      <div className="text-xs leading-relaxed flex-1" style={{ color: "rgba(138,144,178,1)" }}>
        {props.description}
      </div>

      {props.note ? (
        <div className="mt-2 text-[10px]" style={{ color: "rgba(138,144,178,0.6)" }}>
          {props.note}
        </div>
      ) : null}

      <div className="mt-3">
        {props.completed ? (
          <div
            className="flex items-center gap-1.5 text-xs font-medium"
            style={{ color: "rgba(34, 197, 94, 1)" }}
          >
            <Check className="h-3.5 w-3.5" />
            Completed
          </div>
        ) : props.href ? (
          <a
            href={props.href}
            className="btn-press inline-block rounded-xl px-3 py-1.5 text-xs font-medium transition-colors hover:bg-white/5"
            style={{
              backgroundColor: "rgba(99, 102, 241, 0.15)",
              border: "1px solid rgba(99, 102, 241, 0.35)",
              color: "rgba(255,255,255,0.9)",
            }}
          >
            {props.actionLabel}
          </a>
        ) : props.onAction ? (
          <button
            type="button"
            onClick={props.onAction}
            disabled={props.disabled}
            className="btn-press rounded-xl px-3 py-1.5 text-xs font-medium transition-colors hover:bg-white/5"
            style={{
              backgroundColor: "rgba(99, 102, 241, 0.15)",
              border: "1px solid rgba(99, 102, 241, 0.35)",
              color: props.disabled ? "rgba(255,255,255,0.5)" : "rgba(255,255,255,0.9)",
            }}
          >
            {props.actionLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function AccountCard(props: {
  provider: string;
  providerLabel: string;
  connected: boolean;
  username: string | null;
  isPrimary: boolean;
  onUnlink: () => void;
}) {
  return (
    <div
      className="rounded-2xl border p-4 flex items-center justify-between"
      style={{
        borderColor: "rgba(255,255,255,0.08)",
        backgroundColor: "rgba(24, 24, 27, 0.35)",
      }}
    >
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold">{props.providerLabel}</span>
          {props.isPrimary ? (
            <span
              className="rounded-full px-2 py-0.5 text-[10px] font-bold"
              style={{
                backgroundColor: "rgba(99, 102, 241, 0.15)",
                color: "rgba(165, 180, 252, 1)",
              }}
            >
              Primary login
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-sm" style={{ color: "rgba(138,144,178,1)" }}>
          {props.connected ? `Connected as ${props.username ?? "—"}` : "Not connected"}
        </div>
      </div>

      {props.connected && !props.isPrimary ? (
        <button
          type="button"
          onClick={props.onUnlink}
          className="btn-press rounded-xl border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-white/5"
          style={{
            borderColor: "rgba(220, 38, 38, 0.3)",
            color: "rgba(248, 113, 113, 1)",
          }}
        >
          Unlink
        </button>
      ) : null}
    </div>
  );
}

export function InputCard(props: {
  label: string;
  description: string;
  placeholder: string;
  value: string;
  isSaving: boolean;
  onSave: (value: string) => void;
}) {
  const [value, setValue] = useState(props.value);
  const [isDirty, setIsDirty] = useState(false);

  return (
    <div
      className="rounded-2xl border p-4 flex flex-col"
      style={{
        borderColor: "rgba(255,255,255,0.08)",
        backgroundColor: "rgba(24, 24, 27, 0.25)",
      }}
    >
      <div className="text-xs font-semibold" style={{ color: "rgba(230,233,242,0.95)" }}>
        {props.label}
      </div>
      <div className="mt-1 text-[11px] leading-relaxed" style={{ color: "rgba(138,144,178,0.7)" }}>
        {props.description}
      </div>
      <input
        value={value}
        onChange={(e) => {
          setValue(e.target.value);
          setIsDirty(true);
        }}
        placeholder={props.placeholder}
        className="mt-3 w-full rounded-xl border bg-transparent px-3 py-2 text-sm outline-none placeholder:text-white/20 focus:ring-1 focus:ring-[rgba(138,92,255,0.4)] focus:border-[rgba(138,92,255,0.4)]"
        style={{
          borderColor: "rgba(255,255,255,0.10)",
          color: "rgba(230,233,242,0.95)",
        }}
      />
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          onClick={() => {
            props.onSave(value);
            setIsDirty(false);
          }}
          disabled={!isDirty || props.isSaving}
          className="btn-press rounded-xl px-3 py-1.5 text-xs font-medium disabled:opacity-40 transition-colors hover:bg-white/5"
          style={{
            backgroundColor: "rgba(99, 102, 241, 0.15)",
            border: "1px solid rgba(99, 102, 241, 0.35)",
          }}
        >
          {props.isSaving ? "Saving..." : "Save"}
        </button>
      </div>
    </div>
  );
}

export function formatStatus(status: string): string {
  const map: Record<string, string> = {
    not_started: "Not started",
    in_progress: "In progress",
    completed: "Completed",
    skipped: "Skipped",
  };
  return map[status] ?? status;
}

export function statusColor(status: string | null): string {
  if (!status) return "rgba(230,233,242,0.95)";
  const map: Record<string, string> = {
    not_started: "rgba(138,144,178,1)",
    in_progress: "rgba(250, 204, 21, 1)",
    completed: "rgba(34, 197, 94, 1)",
    skipped: "rgba(138,144,178,0.7)",
  };
  return map[status] ?? "rgba(230,233,242,0.95)";
}

export function statusBg(status: string): string {
  const map: Record<string, string> = {
    not_started: "rgba(138,144,178,0.12)",
    in_progress: "rgba(250, 204, 21, 0.12)",
    completed: "rgba(34, 197, 94, 0.12)",
    skipped: "rgba(138,144,178,0.08)",
  };
  return map[status] ?? "rgba(138,144,178,0.12)";
}
