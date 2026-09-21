import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

type MarkdownProps = {
  content: string;
  // Given, links open in the side panel instead of a new tab
  onLinkClick?: (href: string, label: string) => void;
  // An extra class for places that need tighter type than a full write-up, like a day's activities
  className?: string;
};

export default function Markdown({ content, onLinkClick, className }: MarkdownProps) {
  const components: Components = {
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        onClick={(event) => {
          // Let ⌘/Ctrl-click, middle-click and the like open a tab as usual
          if (!onLinkClick || !href || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
          event.preventDefault();
          onLinkClick(href, typeof children === "string" ? children : (event.currentTarget.textContent ?? href));
        }}
      >
        {children}
      </a>
    ),
    table: ({ children }) => (
      <div className="table-wrap">
        <table>{children}</table>
      </div>
    ),
  };

  return (
    <div className={className ? `plan-content ${className}` : "plan-content"}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
