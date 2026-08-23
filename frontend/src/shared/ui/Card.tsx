import type { ReactNode } from "react";

export function Card({
  children,
  title,
  className = "",
}: {
  children: ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <section className={`card ${className}`.trim()}>
      {title && <h2 className="card__title">{title}</h2>}
      {children}
    </section>
  );
}
