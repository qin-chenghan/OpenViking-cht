import { createHash } from "node:crypto";
import { homedir } from "node:os";
import { resolve } from "node:path";

type ContentBlock = { type?: unknown; text?: unknown };
type MessageLike = { role?: unknown; content?: unknown };
const REF_ID_RE = /\[REF_ID: ([a-f0-9]{32})\]/i;
/** Strict MD5 hex pattern — only 32 hex chars (case-insensitive) allowed as refId */
const STRICT_REF_ID_RE = /^[a-f0-9]{32}$/i;

export function md5Hex(input: string): string {
  return createHash("md5").update(input).digest("hex");
}

export function hasRefId(text: string): boolean {
  return REF_ID_RE.test(text);
}

/**
 * Extract and validate a refId from a string.
 * - If the string matches [REF_ID: <hash>], extract the hash.
 * - Otherwise, treat the trimmed string as a raw refId.
 * - Returns null if the result is not a valid 32-char hex MD5 hash.
 * - Returned value is always lowercase for consistent file naming.
 */
export function normalizeRefId(value: string): string | null {
  const match = value.match(REF_ID_RE);
  const candidate = match ? match[1] : value.trim();
  return STRICT_REF_ID_RE.test(candidate) ? candidate.toLowerCase() : null;
}

export function resolveHomePath(pathValue: string): string {
  if (!pathValue) {
    return pathValue;
  }
  return pathValue.startsWith("~/")
    ? resolve(homedir(), pathValue.slice(2))
    : resolve(pathValue);
}

export function extractTextContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((block: ContentBlock) =>
        block && typeof block === "object" && typeof block.text === "string" ? block.text : "",
      )
      .filter(Boolean)
      .join("\n");
  }
  if (content && typeof content === "object") {
    try {
      return JSON.stringify(content);
    } catch {
      return String(content);
    }
  }
  return "";
}

export function setTextContent(message: MessageLike, text: string): MessageLike {
  return { ...message, content: [{ type: "text", text }] };
}

export function isToolRole(role: unknown): boolean {
  return role === "tool" || role === "toolResult" || role === "tool_result";
}

/**
 * Check if message content contains only text blocks (no images, audio, etc.)
 * Returns false if content is an array with non-text blocks (e.g., image_url)
 */
export function isPureTextContent(content: unknown): boolean {
  if (typeof content === "string" || !content) {
    return true;
  }
  if (!Array.isArray(content)) {
    return true;
  }
  return content.every((block) => {
    if (!block || typeof block !== "object") {
      return false;
    }
    const blockType = (block as ContentBlock).type;
    return !blockType || blockType === "text";
  });
}

export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

export function estimateTokensForMessages(messages: MessageLike[]): number {
  return messages.reduce((sum, msg) => sum + estimateTokens(extractTextContent(msg.content)), 0);
}

/**
 * Check if message content matches the standard OpenClaw tool result format:
 * Array<{ type: "text"; text: string }>
 * Returns false if structure is unexpected or contains non-text blocks.
 */
export function isStandardToolResultContent(content: unknown): boolean {
  // Reject: null/undefined/非数组/空数组
  if (!Array.isArray(content) || content.length === 0) {
    return false;
  }
  // Accept: 非空数组，每个块都是 { type: "text", text: string }
  return content.every((block) => {
    if (!block || typeof block !== "object") {
      return false;
    }
    const blockObj = block as ContentBlock;
    return blockObj.type === "text" && typeof blockObj.text === "string";
  });
}
