import React, { useState } from "react";

function App() {
  const [question, setQuestion] = useState<string>("");
  const [response, setResponse] = useState<any>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!question.trim()) return;

    setIsLoading(true);
    setError(null);
    setResponse(null);

    try {
      const res = await fetch("http://localhost:8000/assistant/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ user_question: question }),
      });

      if (!res.ok) {
        const errorData = await res
          .json()
          .catch(() => ({ detail: "Unknown error occurred" }));
        throw new Error(
          errorData.detail || `HTTP error! status: ${res.status}`
        );
      }

      const data = await res.json();
      setResponse(data);
    } catch (err: any) {
      setError(err.message || "Failed to fetch response from assistant.");
      console.error("Error fetching from assistant:", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="w-full h-full">
      <div className="bg-bgcol-000 font-sans text-white min-h-screen tracking-tight flex flex-col h-full w-full">
        <Header />
      </div>
    </div>
  );
}

function Header() {
  return (
    <header className="px-4 py-3">
      <div>
        <span className="italic font-black tracking-normal">Bip Assist</span>
      </div>

      <ul>
        <li></li>
      </ul>
    </header>
  );
}

export default App;
