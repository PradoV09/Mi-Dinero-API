import { useEffect, useState } from "react";
import { Wallet } from "lucide-react";
import { getHealth } from "../services/api";

type State = "loading" | "ok" | "error";

export default function Home() {
  const [state, setState] = useState<State>("loading");

  useEffect(() => {
    getHealth()
      .then((d) => setState(d.status === "ok" ? "ok" : "error"))
      .catch(() => setState("error"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", padding: "2rem", maxWidth: 480, margin: "0 auto" }}>
      <h1 style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <Wallet aria-hidden /> Mi Dinero
      </h1>
      <p role="status">
        {state === "loading" && "Conectando con la API…"}
        {state === "ok" && "API conectada ✅"}
        {state === "error" && "No se pudo conectar con la API ❌"}
      </p>
    </main>
  );
}
