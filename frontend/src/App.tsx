import { Navigate, Route, Routes } from "react-router-dom";
import { ROLES_GESTION, ROLES_QUI_RESERVENT } from "./auth/acces.ts";
import { RouteInvite, RouteProtegee } from "./auth/RouteProtegee.tsx";
import Gabarit from "./components/layout/Gabarit.tsx";
import ConnexionPage from "./pages/ConnexionPage.tsx";
import GestionReservationsPage from "./pages/GestionReservationsPage.tsx";
import GestionSallesPage from "./pages/GestionSallesPage.tsx";
import GestionUtilisateursPage from "./pages/GestionUtilisateursPage.tsx";
import IntrouvablePage from "./pages/IntrouvablePage.tsx";
import MesReservationsPage from "./pages/MesReservationsPage.tsx";
import PlanningPage from "./pages/PlanningPage.tsx";

/**
 * Routes de l'application. Les gardes affinent l'affichage ; l'API refuse
 * de toute façon ce que le rôle ne permet pas.
 */
export default function App() {
  return (
    <Routes>
      <Route
        path="/connexion"
        element={
          <RouteInvite>
            <ConnexionPage />
          </RouteInvite>
        }
      />
      <Route
        element={
          <RouteProtegee>
            <Gabarit />
          </RouteProtegee>
        }
      >
        <Route index element={<Navigate to="/planning" replace />} />
        <Route path="planning" element={<PlanningPage />} />
        <Route
          path="mes-reservations"
          element={
            <RouteProtegee roles={ROLES_QUI_RESERVENT}>
              <MesReservationsPage />
            </RouteProtegee>
          }
        />
        <Route path="gestion">
          <Route index element={<Navigate to="/gestion/reservations" replace />} />
          <Route
            path="reservations"
            element={
              <RouteProtegee roles={ROLES_GESTION}>
                <GestionReservationsPage />
              </RouteProtegee>
            }
          />
          <Route
            path="salles"
            element={
              <RouteProtegee roles={ROLES_GESTION}>
                <GestionSallesPage />
              </RouteProtegee>
            }
          />
          <Route
            path="utilisateurs"
            element={
              <RouteProtegee roles={ROLES_GESTION}>
                <GestionUtilisateursPage />
              </RouteProtegee>
            }
          />
        </Route>
        <Route path="*" element={<IntrouvablePage />} />
      </Route>
    </Routes>
  );
}
