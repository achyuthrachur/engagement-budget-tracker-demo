import { createRoot } from "react-dom/client";
import App from "./App";

// Set before the first paint (matches legacy app.js's own top-level
// assignment) so switching pages never flashes the wrong theme.
document.documentElement.dataset.theme = localStorage.getItem("budget-theme") || "light";

createRoot(document.getElementById("root")).render(<App />);
