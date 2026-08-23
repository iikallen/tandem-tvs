export function Avatar({
  name,
  imageUrl,
  size = "md",
}: {
  name: string;
  imageUrl?: string;
  size?: "md" | "lg";
}) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
  return (
    <span className={`avatar avatar--${size}`} aria-hidden="true">
      {imageUrl ? <img src={imageUrl} alt="" /> : initials}
    </span>
  );
}
