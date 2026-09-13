/** Minimal markdown renderer: headings, bold, inline code, lists, rules. */
const RULES = [
  { re: /^###\s+(.*)/, tag: "h3" },
  { re: /^##\s+(.*)/, tag: "h2" },
  { re: /^#\s+(.*)/, tag: "h1" },
];

function inline(text, keyPrefix) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let match;
  let key = 0;
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={`${keyPrefix}-${key++}`}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<code key={`${keyPrefix}-${key++}`}>{token.slice(1, -1)}</code>);
    }
    last = match.index + token.length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length > 0 ? parts : [text];
}

export function Markdown({ text }) {
  const lines = String(text ?? "").split("\n");
  const blocks = [];
  let listItems = [];
  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {listItems.map((item, i) => (
            <li key={i}>{inline(item, `li-${blocks.length}-${i}`)}</li>
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  lines.forEach((line, idx) => {
    const stripped = line.trim();
    if (stripped === "") {
      flushList();
      return;
    }
    if (/^(-{3,}|\*{3,})$/.test(stripped)) {
      flushList();
      blocks.push(<hr key={`hr-${idx}`} />);
      return;
    }
    const listMatch = /^[-*]\s+(.*)/.exec(stripped);
    if (listMatch) {
      listItems.push(listMatch[1]);
      return;
    }
    const numbered = /^\d+[.)]\s+(.*)/.exec(stripped);
    if (numbered) {
      listItems.push(numbered[1]);
      return;
    }
    flushList();
    for (const rule of RULES) {
      const match = rule.tag && rule.re.exec(stripped);
      if (match) {
        const Tag = rule.tag;
        blocks.push(<Tag key={`h-${idx}`}>{inline(match[1], `h-${idx}`)}</Tag>);
        return;
      }
    }
    blocks.push(<p key={`p-${idx}`}>{inline(stripped, `p-${idx}`)}</p>);
  });
  flushList();

  return <div className="md">{blocks}</div>;
}
