import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.tsx";
import { FournisseurAuth } from "./auth/AuthContext.tsx";
import "./styles.css";

const racine = document.getElementById("root");
if (!racine) throw new Error("Élément #root introuvable dans index.html");

createRoot(racine).render(
  <StrictMode>
    <BrowserRouter>
      <FournisseurAuth>
        <App />
      </FournisseurAuth>
    </BrowserRouter>
  </StrictMode>,
);
