import type { ReactElement } from "react";

type ActionIconName =
  | "home"
  | "back"
  | "edit"
  | "trash"
  | "restore"
  | "power"
  | "key"
  | "refresh"
  | "close"
  | "plus"
  | "eye"
  | "eye-off"
  | "download"
  | "check"
  | "users";

const paths: Record<ActionIconName, string> = {
  home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  back: "m12 19-7-7 7-7M5 12h14",
  edit: "m16 3 5 5-12 12-6 1 1-6zM14 5l5 5",
  trash: "M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7",
  restore: "M3 10a9 9 0 1 1 2 8M3 4v6h6M12 7v5l3 2",
  power: "M12 2v10M6 5a9 9 0 1 0 12 0",
  key: "M15 7a5 5 0 1 1-4 8L3 23H1v-4l8-8a5 5 0 0 1 6-4zM16 10h.01",
  refresh: "M20 7a9 9 0 0 0-15-2L2 8m0-6v6h6M4 17a9 9 0 0 0 15 2l3-3m0 6v-6h-6",
  close: "m6 6 12 12M6 18 18 6",
  plus: "M12 5v14M5 12h14",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
  "eye-off": "m3 3 18 18M10.6 5.1 12 5c6.5 0 10 7 10 7a20 20 0 0 1-3 3.8M6.3 6.3A23 23 0 0 0 2 12s3.5 7 10 7a12 12 0 0 0 5.7-1.3M10 10a3 3 0 0 0 4 4",
  download: "M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5",
  check: "m5 12 4 4L19 6",
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.9M15 3.1a4 4 0 0 1 0 7.8M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
};

export function ActionIcon({ name }: { name: ActionIconName }): ReactElement {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-5 shrink-0"
    >
      <path d={paths[name]} />
    </svg>
  );
}
