"use client";

import { useState, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

function CodeBlock({ className, children }: { className?: string; children: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const match = /language-(\w+)/.exec(className || "");
  const lang = match ? match[1] : "";
  const code = String(children).replace(/\n$/, "");

  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!match) {
    // Inline code
    return (
      <code className="px-1.5 py-0.5 rounded text-[0.85em]"
        style={{ background: "var(--bg-tertiary)", color: "hsl(270,70%,75%)" }}>
        {children}
      </code>
    );
  }

  return (
    <div className="relative group rounded-lg overflow-hidden my-3"
      style={{ border: "1px solid var(--border)" }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-1.5 text-[10px]"
        style={{ background: "var(--bg-tertiary)", color: "var(--text-muted)" }}>
        <span>{lang}</span>
        <button
          onClick={handleCopy}
          className="opacity-0 group-hover:opacity-100 transition-opacity px-2 py-0.5 rounded hover:text-[var(--text-primary)]"
        >
          {copied ? "✓ 복사됨" : "복사"}
        </button>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={lang}
        PreTag="div"
        customStyle={{
          margin: 0,
          padding: "1em",
          fontSize: "0.8em",
          background: "var(--bg-secondary)",
          borderRadius: 0,
        }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

const markdownComponents: Components = {
  code({ className, children, ...props }) {
    const isBlock = className?.includes("language-");
    if (isBlock) {
      return <CodeBlock className={className}>{children}</CodeBlock>;
    }
    return (
      <code className="px-1.5 py-0.5 rounded text-[0.85em]"
        style={{ background: "var(--bg-tertiary)", color: "hsl(270,70%,75%)" }}
        {...props}>
        {children}
      </code>
    );
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3">
        <table className="w-full text-sm" style={{ borderCollapse: "collapse" }}>
          {children}
        </table>
      </div>
    );
  },
  th({ children }) {
    return (
      <th className="text-left text-xs font-semibold px-3 py-2"
        style={{ background: "var(--bg-tertiary)", color: "var(--text-secondary)", border: "1px solid var(--border)" }}>
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="px-3 py-2 text-xs"
        style={{ border: "1px solid var(--border)", color: "var(--text-secondary)" }}>
        {children}
      </td>
    );
  },
};

interface MarkdownRendererProps {
  content: string;
}

export default function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <div className="text-sm leading-relaxed prose prose-invert prose-sm max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        components={markdownComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
