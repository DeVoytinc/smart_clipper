import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./routes/Dashboard.jsx";
import ProjectEditor from "./routes/ProjectEditor.jsx";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/editor/:projectId" element={<ProjectEditor />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
