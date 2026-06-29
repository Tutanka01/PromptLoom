import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { DashboardPage } from "./features/dashboard/DashboardPage";
import { CreatePage } from "./features/create/CreatePage";
import { JobPage } from "./features/job/JobPage";
import { BatchPage } from "./features/batch/BatchPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "create", element: <CreatePage /> },
      { path: "videos/:jobId", element: <JobPage /> },
      { path: "batches/:batchId", element: <BatchPage /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
