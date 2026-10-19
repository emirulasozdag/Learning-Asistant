import { RouterProvider } from "react-router";

import AuthProvider from "./auth/AuthProvider";
import { router } from "./router";
import ToastProvider from "./ui/toast/ToastProvider";

export default function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </AuthProvider>
  );
}
