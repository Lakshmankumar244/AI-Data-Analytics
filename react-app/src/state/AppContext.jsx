import { createContext, useContext, useReducer, useMemo } from "react";
import { reducer } from "./reducer";
import { buildInitialState } from "./initialState";

const AppStateContext = createContext(null);
const AppDispatchContext = createContext(null);

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, undefined, buildInitialState);

  return (
    <AppStateContext.Provider value={state}>
      <AppDispatchContext.Provider value={dispatch}>
        {children}
      </AppDispatchContext.Provider>
    </AppStateContext.Provider>
  );
}

export function useAppState() {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used within AppProvider");
  return ctx;
}

export function useAppDispatch() {
  const ctx = useContext(AppDispatchContext);
  if (!ctx) throw new Error("useAppDispatch must be used within AppProvider");
  return ctx;
}

// Convenience action creators - components call these instead of
// dispatching raw action objects, mirroring the original widget's
// context-provided helper functions (setScanConfig, setRules, setTab...).
export function useActions() {
  const dispatch = useAppDispatch();
  return useMemo(
    () => ({
      setScanConfig: (patch) => dispatch({ type: "setScanConfig", patch }),
      setRules: (patch) => dispatch({ type: "setRules", patch }),
      setTab: (tab) => dispatch({ type: "setTab", tab }),
      setFilter: (patch) => dispatch({ type: "setFilter", patch }),
      showHome: () => dispatch({ type: "showHome" }),
      showSetup: () => dispatch({ type: "showSetup" }),
      reset: () => dispatch({ type: "reset" }),
    }),
    [dispatch]
  );
}
