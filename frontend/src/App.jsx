import { BrowserRouter, Route, Routes } from "react-router-dom";
import Overview from "./pages/Overview";
import Import from "./pages/Import";
import Exceptions from "./pages/Exceptions";
import Phases from "./pages/Phases";
import PhaseDetail from "./pages/PhaseDetail";
import HoursOverages from "./pages/HoursOverages";
import Dashboard from "./pages/Dashboard";
import Landing from "./pages/Landing";
import Help from "./pages/Help";
import { EngagementLayout } from "./components/EngagementLayout";
import { GlobalStyle } from "./styles/GlobalStyle";

// Only routes Flask actually hands the React bundle to are declared here
// (see app.py's serve_frontend()/index()). Every other path - /proposals,
// /engagements/<id>/phases, /settings, etc. - is still a full navigation
// to the legacy vanilla-JS app, so it deliberately has no matching <Route>:
// the browser leaves the SPA before React Router ever sees the URL.
// /engagements/:id is a layout route (EngagementLayout: AppShell + topbar +
// EngagementTabs + <Outlet>) as of the Weekly Import port - add further
// React-owned sub-pages as their own child <Route> here, not siblings.
export default function App() {
  return (
    <BrowserRouter>
      <GlobalStyle />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/help" element={<Help />} />
        <Route path="/engagements/:id" element={<EngagementLayout />}>
          <Route index element={<Overview />} />
          <Route path="import" element={<Import />} />
          <Route path="exceptions" element={<Exceptions />} />
          <Route path="phases" element={<Phases />} />
          <Route path="phases/:phaseId" element={<PhaseDetail />} />
          <Route path="hours-overages" element={<HoursOverages />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
