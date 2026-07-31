import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type UiMode = "simple" | "advanced";

type ModeContextValue = {
  mode: UiMode;
  setMode: (mode: UiMode) => void;
  isAdvanced: boolean;
};

const ModeContext = createContext<ModeContextValue | null>(null);

export function ModeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<UiMode>(() => {
    return (localStorage.getItem("dot1x_mode") as UiMode) || "simple";
  });

  const value = useMemo(
    () => ({
      mode,
      setMode: (next: UiMode) => {
        localStorage.setItem("dot1x_mode", next);
        setMode(next);
      },
      isAdvanced: mode === "advanced",
    }),
    [mode],
  );

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
}

export function useMode() {
  const ctx = useContext(ModeContext);
  if (!ctx) throw new Error("useMode must be used within ModeProvider");
  return ctx;
}
