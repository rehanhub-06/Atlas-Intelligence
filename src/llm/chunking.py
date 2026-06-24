def chunk_text(text, keep_head_pct=0.3, keep_tail_pct=0.1):
    if not text:
        return ""
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    n = len(paragraphs)
    if n == 0:
        return text[:1000] # Fallback for flat unformatted text
    head = paragraphs[: max(1, int(n * keep_head_pct))]
    tail = paragraphs[-max(1, int(n * keep_tail_pct)):] if keep_tail_pct else []
    return "\n\n".join(head + ["...[truncated]..."] + tail)
