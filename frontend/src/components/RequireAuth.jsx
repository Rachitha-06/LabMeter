import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext.jsx";
import { LoadingState } from "./States.jsx";

export default function RequireAuth({ children }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "checking") return <LoadingState label="Checking your session…" />;
  if (status !== "signed_in") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return children;
}
