import { useEffect, useState } from "react";

import CameraScreen from "./screens/CameraScreen";

import ProcessingScreen from "./screens/ProcessingScreen";
import type { ProcessingStage } from "./screens/ProcessingScreen";

import ResultScreen from "./screens/ResultScreen";
import HistoryScreen from "./screens/HistoryScreen";

import TopNav from "./components/TopNav";
import DockNavigation from "./components/DockNavigation";

type Screen = "camera" | "processing" | "result" | "history";

const INITIAL_STAGES: ProcessingStage[] = [
  { id: "upload", label: "Image Uploaded", status: "pending" },
  { id: "ocr", label: "Extracting Text", status: "pending" },
  { id: "llm", label: "Generating your response", status: "pending" },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("camera");
  const [stages, setStages] = useState<ProcessingStage[]>(INITIAL_STAGES);
  const [extractedData, setExtractedData] = useState<Record<string, string | null> | null>(null);
  const [serialNumber, setSerialNumber] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeNavItem, setActiveNavItem] = useState<string>("scan");
  const [cameraSessionKey, setCameraSessionKey] = useState(0);

  useEffect(() => {
    if (!error) {
      return;
    }

    const timer = window.setTimeout(() => {
      setError(null);
      setStages(INITIAL_STAGES);
      setActiveNavItem("scan");
      setScreen("camera");
    }, 3000);

    return () => {
      window.clearTimeout(timer);
    };
  }, [error]);

  /*
   * =====================================================
   * NAVIGATION
   * =====================================================
   */
  const handleNavigation = (tab: string) => {
    setActiveNavItem(tab);

    if (tab === "home") {
      setScreen("processing");
      setActiveNavItem("home");
    } else if (tab === "scan") {
      setScreen("camera");
      setActiveNavItem("scan");
    } else if (tab === "history") {
      setScreen("history");
    }
  };

  /*
   * =====================================================
   * PROCESSING STAGE
   * =====================================================
   */
  const updateStage = (id: string, status: ProcessingStage["status"], message?: string) => {
    setStages((previous) =>
      previous.map((stage) =>
        stage.id === id ? { ...stage, status, message } : stage
      )
    );
  };

  /*
   * =====================================================
   * RESET
   * =====================================================
   */
  const handleReset = () => {
    setStages(INITIAL_STAGES);
    setExtractedData(null);
    setSerialNumber(null);
    setError(null);
    setActiveNavItem("scan");
    setCameraSessionKey((previous) => previous + 1);
    setScreen("camera");
  };

  /*
   * =====================================================
   * DOCUMENT PROCESSING
   * =====================================================
   */
  const handleProceed = async (images: Blob[]) => {
    if (!images.length) {
      return;
    }

    setStages(INITIAL_STAGES);
    setError(null);
    setScreen("processing");
    setActiveNavItem("scan");

    const formData = new FormData();
    images.forEach((blob, index) => {
      const fileName = `page-${index + 1}.jpg`;
      formData.append("files", blob, fileName);
    });

    try {
      updateStage("upload", "processing", `Uploading ${images.length} image${images.length > 1 ? "s" : ""}...`);
      await new Promise((resolve) => setTimeout(resolve, 500));
      updateStage("upload", "complete");

      const apiUrl = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
      const fetchPromise = fetch(`${apiUrl}/upload/`, {
        method: "POST",
        body: formData,
      });

      updateStage("ocr", "processing", "Running text extraction...");
      await new Promise((resolve) => setTimeout(resolve, 1500));
      updateStage("ocr", "complete");

      updateStage("llm", "processing", "Generating your response...");
      const response = await fetchPromise;

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();
      updateStage("llm", "complete");

      setSerialNumber(data.serial_number ?? null);
      setExtractedData(data.extracted_data);
      setScreen("result");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Unknown error";
      setError("Something went wrong. Please try again later.");
      updateStage("upload", "error", message);
      updateStage("ocr", "error");
      updateStage("llm", "error");
    }
  };

  /*
   * =====================================================
   * GLOBAL APP LAYOUT
   * =====================================================
   */
  return (
    <div className="app">
      <TopNav />
      <main className="viewport" id="content">
        <div className={`screen ${screen === "camera" ? "active" : ""}`} id="capture" data-od-id="capture-screen">
          <CameraScreen key={cameraSessionKey} onAccept={handleProceed} />
        </div>
        <div className={`screen ${screen === "processing" ? "active" : ""}`} id="processing" data-od-id="processing-screen">
          <ProcessingScreen
            stages={stages}
            session={{ source: "Camera", timestamp: new Date().toLocaleString() }}
            onAbort={handleReset}
            error={error}
          />
        </div>
        <div className={`screen ${screen === "history" ? "active" : ""}`} id="history" data-od-id="history-screen">
          <HistoryScreen />
        </div>
        <div className={`screen ${screen === "result" ? "active" : ""}`} id="result" data-od-id="result-screen">
          {extractedData && (
            <ResultScreen data={extractedData} serialNumber={serialNumber ?? undefined} error={error ?? undefined} onProcessAnother={handleReset} />
          )}
        </div>
      </main>
      <DockNavigation currentTab={activeNavItem} onTabChange={handleNavigation} />
    </div>
  );
}