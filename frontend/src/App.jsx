import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import RequireAuth from "./components/RequireAuth.jsx";
import { EmptyState } from "./components/States.jsx";
import Alerts from "./pages/Alerts.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Energy from "./pages/Energy.jsx";
import Forecasts from "./pages/Forecasts.jsx";
import Import from "./pages/Import.jsx";
import LabDetail from "./pages/LabDetail.jsx";
import Labs from "./pages/Labs.jsx";
import Login from "./pages/Login.jsx";
import Readings from "./pages/Readings.jsx";
import Users from "./pages/Users.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="login" element={<Login />} />
      <Route element={<RequireAuth><Layout /></RequireAuth>}>
        <Route index element={<Dashboard />} />
        <Route path="labs" element={<Labs />} />
        <Route path="labs/:id" element={<LabDetail />} />
        <Route path="readings" element={<Readings />} />
        <Route path="forecasts" element={<Forecasts />} />
        <Route path="alerts" element={<Alerts />} />
        <Route path="energy" element={<Energy />} />
        <Route path="import" element={<Import />} />
        <Route path="users" element={<Users />} />
        <Route path="*" element={<EmptyState title="Page not found" />} />
      </Route>
    </Routes>
  );
}
