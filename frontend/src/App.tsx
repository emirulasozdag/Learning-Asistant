import { RouterProvider } from "react-router";

import AuthProvider from "./auth/AuthProvider";
import { router } from "./router";

export default function App() {
  return (
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  );
}
