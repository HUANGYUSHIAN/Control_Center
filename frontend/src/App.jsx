import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  FormControl,
  Divider,
  IconButton,
  InputAdornment,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import SendIcon from "@mui/icons-material/Send";
import MicIcon from "@mui/icons-material/Mic";
import MicOffIcon from "@mui/icons-material/MicOff";
import VisibilityIcon from "@mui/icons-material/Visibility";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import PauseIcon from "@mui/icons-material/Pause";
import StopIcon from "@mui/icons-material/Stop";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import SpeechRecognition, { useSpeechRecognition } from "react-speech-recognition";
import { Event, Role } from "./protocol";

const ACCENT = "#76B82D";

function nowText() {
  return new Date().toLocaleTimeString();
}

function makeId() {
  // 部分瀏覽器/環境沒有 crypto.randomUUID
  if (typeof crypto !== "undefined" && crypto && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

const LANG_OPTIONS = [
  { id: "zh-TW", label: "繁體中文" },
  { id: "en-US", label: "English" },
  { id: "ja-JP", label: "日本語" }
];

const I18N = {
  "zh-TW": {
    appTitle: "控制中心",
    processBoardTitle: "流程面板",
    displayBoardTitle: "顯示面板",
    commandBoardTitle: "指令面板",
    overallProcess: "整體流程",
    statusWaiting: "等待中（等待 worker 連線）",
    statusReady: "初始化完成",
    statusRunning: "執行中",
    statusPaused: "已暫停",
    statusIdle: "閒置／已停止",
    btnPause: "暫停任務",
    btnResume: "繼續",
    btnStop: "停止任務",
    tabDigital: "數位視角",
    tabCamera: "相機視角",
    tabRobotStatus: "機器人狀態",
    commandPlaceholder: "輸入自然語言指令",
    logsEmpty: "尚無紀錄",
    robotStatusNone: "無狀態（worker 可能未連線）",
    connConnecting: "連線中",
    connConnected: "已連線",
    connError: "連線錯誤",
    connDisconnected: "已斷線",
    initMainTitle: "初始化",
    initChildActplan: "確認 worker_actplan 連線",
    initChildVision: "確認 worker_vision 連線",
    initChildRobot: "確認 worker_robot 連線",
    micToggleLabel: "語音輸入",
    micNotSupported: "此瀏覽器不支援語音辨識（請使用 Chrome / Edge）"
  },
  "en-US": {
    appTitle: "Control Center",
    processBoardTitle: "Process Board",
    displayBoardTitle: "Display Board",
    commandBoardTitle: "Command Board",
    overallProcess: "Overall Process",
    statusWaiting: "Waiting (awaiting worker connections)",
    statusReady: "Initialization complete",
    statusRunning: "Running",
    statusPaused: "Paused",
    statusIdle: "Idle / Stopped",
    btnPause: "Pause Task",
    btnResume: "Resume",
    btnStop: "Stop Task",
    tabDigital: "Digital View",
    tabCamera: "Camera View",
    tabRobotStatus: "Robot Status",
    commandPlaceholder: "Enter a natural language command",
    logsEmpty: "No logs yet",
    robotStatusNone: "No status (worker may be disconnected)",
    connConnecting: "Connecting",
    connConnected: "Connected",
    connError: "Connection error",
    connDisconnected: "Disconnected",
    initMainTitle: "Initialization",
    initChildActplan: "Confirm worker_actplan connection",
    initChildVision: "Confirm worker_vision connection",
    initChildRobot: "Confirm worker_robot connection",
    micToggleLabel: "Voice input",
    micNotSupported: "Speech recognition is not supported in this browser (use Chrome / Edge)"
  },
  "ja-JP": {
    appTitle: "コントロールセンター",
    processBoardTitle: "プロセスボード",
    displayBoardTitle: "ディスプレイボード",
    commandBoardTitle: "コマンドボード",
    overallProcess: "全体の進行状況",
    statusWaiting: "待機中（ワーカーの接続待ち）",
    statusReady: "初期化完了",
    statusRunning: "実行中",
    statusPaused: "一時停止中",
    statusIdle: "待機中／停止済み",
    btnPause: "タスクを一時停止",
    btnResume: "再開",
    btnStop: "タスク停止",
    tabDigital: "デジタルビュー",
    tabCamera: "カメラビュー",
    tabRobotStatus: "ロボット状態",
    commandPlaceholder: "自然言語の指示を入力",
    logsEmpty: "ログはありません",
    robotStatusNone: "ステータスなし（ワーカーが未接続の可能性）",
    connConnecting: "接続中",
    connConnected: "接続済み",
    connError: "接続エラー",
    connDisconnected: "切断",
    initMainTitle: "初期化",
    initChildActplan: "worker_actplan の接続確認",
    initChildVision: "worker_vision の接続確認",
    initChildRobot: "worker_robot の接続確認",
    micToggleLabel: "音声入力",
    micNotSupported: "このブラウザは音声認識に対応していません（Chrome / Edge を使用）"
  }
};

export default function App() {
  const contentRef = useRef(null);
  const [layoutScale, setLayoutScale] = useState(1);
  const [layoutOffset, setLayoutOffset] = useState({ x: 0, y: 0 });
  const [scrollMaxY, setScrollMaxY] = useState(0);
  const [scrollSliderValue, setScrollSliderValue] = useState(100);

  const [lang, setLang] = useState("zh-TW");
  const texts = I18N[lang] || I18N["zh-TW"];
  const [connectionState, setConnectionState] = useState("connecting"); // connecting | connected | error | disconnected
  const [processLogs, setProcessLogs] = useState([]);
  const [displayLogs, setDisplayLogs] = useState([]);
  const [commandLogs, setCommandLogs] = useState([]);
  const [showLogs, setShowLogs] = useState(true);
  const [activeView, setActiveView] = useState("digital");
  const [digitalImage, setDigitalImage] = useState("");
  const [cameraImage, setCameraImage] = useState("");
  const [robotJointNames, setRobotJointNames] = useState([]);
  const [robotJointAngles, setRobotJointAngles] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState([]);
  const [logScroll, setLogScroll] = useState({ process: 100, display: 100, command: 100 });
  const [processTree, setProcessTree] = useState({ overallProgress: 0, runState: "idle", tasks: [] });
  const [selectedSubId, setSelectedSubId] = useState(null);

  const wsRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const rafRef = useRef(null);
  const [micOn, setMicOn] = useState(false);
  const [micSound, setMicSound] = useState(false);
  const micOnRef = useRef(false);
  const { transcript, browserSupportsSpeechRecognition } = useSpeechRecognition();
  micOnRef.current = micOn;

  const stopLevelMonitor = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    analyserRef.current = null;
    if (audioContextRef.current) {
      void audioContextRef.current.close();
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    setMicSound(false);
  }, []);

  const startLevelMonitor = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaStreamRef.current = stream;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    audioContextRef.current = ctx;
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 512;
    analyser.smoothingTimeConstant = 0.35;
    source.connect(analyser);
    analyserRef.current = analyser;

    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      const node = analyserRef.current;
      if (!node) return;
      node.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const v = (buf[i] - 128) / 128;
        sum += v * v;
      }
      const rms = Math.sqrt(sum / buf.length);
      setMicSound(rms > 0.035);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
  }, []);

  const handleMicToggle = async () => {
    if (!browserSupportsSpeechRecognition) {
      pushLog("command", texts.micNotSupported, "warning");
      return;
    }
    if (micOn) {
      await SpeechRecognition.stopListening();
      stopLevelMonitor();
      setMicOn(false);
      return;
    }
    try {
      await startLevelMonitor();
      await SpeechRecognition.startListening({ continuous: true, language: lang });
      setMicOn(true);
    } catch (e) {
      stopLevelMonitor();
      void SpeechRecognition.stopListening().catch(() => {});
      pushLog("command", `麥克風: ${e?.message || String(e)}`, "error");
    }
  };

  // 僅在「語言」變更且麥克風已開啟時重啟辨識（用 ref 讀 micOn，避免依賴 micOn 造成開麥時多一次 stop/start）
  useEffect(() => {
    if (!micOnRef.current) return;
    let cancelled = false;
    void (async () => {
      await SpeechRecognition.stopListening();
      if (cancelled) return;
      await SpeechRecognition.startListening({ continuous: true, language: lang });
    })();
    return () => {
      cancelled = true;
    };
  }, [lang]);

  useEffect(() => {
    return () => {
      void SpeechRecognition.stopListening();
      stopLevelMonitor();
    };
  }, [stopLevelMonitor]);

  const wsUrl = useMemo(() => {
    const host = window.location.hostname || "127.0.0.1";
    return `ws://${host}:8765/ws`;
  }, []);

  const getLocalizedTaskTitle = (taskId, fallbackTitle) => {
    if (taskId === "init") return texts.initMainTitle;
    if (taskId === "init-1") return texts.initChildActplan;
    if (taskId === "init-2") return texts.initChildVision;
    if (taskId === "init-3") return texts.initChildRobot;
    return fallbackTitle;
  };

  const pushLog = (board, text, level = "info") => {
    const setter = board === "process" ? setProcessLogs : board === "display" ? setDisplayLogs : setCommandLogs;
    setter((prev) => [{ id: makeId(), ts: nowText(), text, level }, ...prev].slice(0, 200));
  };

  useEffect(() => {
    if (transcript) {
      setChatInput(transcript);
    }
  }, [transcript]);

  // 自動依照視窗大小等比例縮放，避免 Process Board 高度偏高必須滑動才能看完整頁面
  useEffect(() => {
    const recompute = () => {
      const el = contentRef.current;
      if (!el) return;
      const naturalW = el.scrollWidth || el.clientWidth;
      const naturalH = el.scrollHeight || el.clientHeight;
      if (!naturalW || !naturalH) return;

      const availW = window.innerWidth;
      const availH = window.innerHeight;

      // 不要放大超過原設計尺度，僅在超出時縮小以完全呈現
      const s = Math.min(availW / naturalW, availH / naturalH, 1);
      const scaledW = naturalW * s;
      const scaledH = naturalH * s;

      const nextScrollMaxY = Math.max(0, scaledH - availH);
      const centerY = (availH - scaledH) / 2; // negative when scaledH > availH
      const nextOffsetY = Math.min(0, Math.max(-nextScrollMaxY, centerY));

      setLayoutScale(s);
      setLayoutOffset({
        x: Math.max(0, (availW - scaledW) / 2),
        y: nextOffsetY
      });
      setScrollMaxY(nextScrollMaxY);
      if (nextScrollMaxY === 0) {
        setScrollSliderValue(100);
      } else {
        // offsetY in [-scrollMaxY, 0] -> slider in [0..100]
        const slider = ((nextOffsetY + nextScrollMaxY) / nextScrollMaxY) * 100;
        setScrollSliderValue(Math.round(slider));
      }
    };

    recompute();
    window.addEventListener("resize", recompute);
    return () => window.removeEventListener("resize", recompute);
  }, []);

  const handlePageScrollSlider = (_e, v) => {
    const slider = typeof v === "number" ? v : 100;
    const nextOffsetY = -scrollMaxY + (scrollMaxY * slider) / 100;
    setLayoutOffset((prev) => ({ ...prev, y: nextOffsetY }));
    setScrollSliderValue(slider);
  };

  const connect = () => {
    if (wsRef.current && wsRef.current.readyState <= 1) {
      return;
    }
    pushLog("process", `連線到 ${wsUrl}`);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnectionState("connected");
      ws.send(JSON.stringify({ event: Event.REGISTER, role: Role.FRONTEND }));
      ws.send(JSON.stringify({ event: Event.SUBSCRIBE_VIEW, view: "digital" }));
      pushLog("process", "WebSocket 已連線並註冊");
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.event === Event.TASK_STATUS) {
        pushLog("process", `${msg.time} ${msg.task} ${msg.status} ${msg.detail || ""}`);
      } else if (msg.event === Event.PROCESS_SNAPSHOT) {
        setProcessTree({
          overallProgress: msg.overallProgress ?? 0,
          runState: msg.runState ?? "idle",
          tasks: Array.isArray(msg.tasks) ? msg.tasks : []
        });
      } else if (msg.event === Event.FRAME) {
        const src = `data:image/jpeg;base64,${msg.image || ""}`;
        if (msg.view === "digital") {
          setDigitalImage(src);
        } else if (msg.view === "camera") {
          setCameraImage(src);
        }
      } else if (msg.event === Event.ROBOT_STATUS_INIT) {
        setRobotJointNames(msg.joints || []);
        pushLog("display", "接收 Robot joints 名稱");
      } else if (msg.event === Event.ROBOT_STATUS_UPDATE) {
        setRobotJointAngles(msg.angles || []);
      } else if (msg.event === Event.COMMAND_REPLY) {
        setChatMessages((prev) => [...prev, { role: "assistant", text: msg.text || "" }]);
        pushLog("command", "收到 worker_actplan 回覆");
      } else if (msg.event === Event.VIEW_STATUS) {
        pushLog("display", `view=${msg.view} status=${msg.status}`);
      } else if (msg.event === Event.ERROR) {
        pushLog("display", msg.message || "未知錯誤", "error");
      }
    };

    ws.onerror = () => {
      setConnectionState("error");
      pushLog("process", "WebSocket 發生錯誤", "error");
    };

    ws.onclose = () => {
      setConnectionState("disconnected");
      wsRef.current = null;
      pushLog("process", "WebSocket 已關閉，5 秒後重連");
      setTimeout(connect, 5000);
    };
  };

  const sendProcessControl = (action) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      pushLog("process", "尚未連線，無法控制流程", "warning");
      return;
    }
    ws.send(JSON.stringify({ event: Event.PROCESS_CONTROL, action }));
    pushLog("process", `流程控制: ${action}`);
  };

  const switchView = (nextView) => {
    const prev = activeView;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setActiveView(nextView);
      return;
    }
    ws.send(JSON.stringify({ event: Event.UNSUBSCRIBE_VIEW, view: prev }));
    ws.send(JSON.stringify({ event: Event.SUBSCRIBE_VIEW, view: nextView }));
    pushLog("display", `切換 ${prev} -> ${nextView}`);
    setActiveView(nextView);
    if (nextView === "camera") setCameraImage("");
    if (nextView === "digital") setDigitalImage("");
    if (nextView === "robot_status") {
      setRobotJointNames([]);
      setRobotJointAngles([]);
    }
  };

  const sendCommand = () => {
    const text = chatInput.trim();
    if (!text) return;
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      pushLog("command", "尚未連線，無法送出指令", "warning");
      return;
    }
    ws.send(JSON.stringify({ event: Event.COMMAND_INPUT, text }));
    setChatMessages((prev) => [...prev, { role: "user", text }]);
    setChatInput("");
    void (async () => {
      await SpeechRecognition.stopListening();
      stopLevelMonitor();
      setMicOn(false);
      setMicSound(false);
    })();
    pushLog("command", `送出指令: ${text}`);
  };

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const renderLogs = (rows, key) => (
    <Box>
      {showLogs && (
        <Box sx={{ mt: 1 }}>
          <Slider
            size="small"
            value={logScroll[key]}
            onChange={(_, v) => setLogScroll((prev) => ({ ...prev, [key]: v }))}
          />
          <Box sx={{ maxHeight: 180, overflowY: "auto", opacity: logScroll[key] / 100 }}>
            {rows.length === 0 ? (
              <Alert severity="info">{texts.logsEmpty}</Alert>
            ) : (
              rows.map((log) => (
                <Alert key={log.id} severity={log.level === "error" ? "error" : log.level === "warning" ? "warning" : "info"} sx={{ mb: 1 }}>
                  [{log.ts}] {log.text}
                </Alert>
              ))
            )}
          </Box>
        </Box>
      )}
    </Box>
  );

  return (
    <Box sx={{ position: "fixed", inset: 0, overflow: "hidden" }}>
      <Box
        ref={contentRef}
        sx={{
          transform: `translate(${layoutOffset.x}px, ${layoutOffset.y}px) scale(${layoutScale})`,
          transformOrigin: "top left",
          width: "100%"
        }}
      >
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
          <Typography variant="h5" fontWeight={700}>{texts.appTitle}</Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Chip
              label={
                connectionState === "connected"
                  ? texts.connConnected
                  : connectionState === "error"
                    ? texts.connError
                    : connectionState === "disconnected"
                      ? texts.connDisconnected
                      : texts.connConnecting
              }
              color={connectionState === "connected" ? "success" : "default"}
            />
            <Chip label={wsUrl} />
            <FormControl size="small" sx={{ minWidth: 130 }}>
              <Select value={lang} onChange={(e) => setLang(e.target.value)} size="small">
                {LANG_OPTIONS.map((opt) => (
                  <MenuItem key={opt.id} value={opt.id}>
                    {opt.label}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
            <IconButton color="primary" onClick={() => setShowLogs((v) => !v)}>
              {showLogs ? <VisibilityIcon /> : <VisibilityOffIcon />}
            </IconButton>
          </Stack>
        </Stack>

        <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
          <Paper
            sx={{
              p: 2,
              flex: 1,
              minHeight: "70vh",
              bgcolor: "#ffffff",
              color: "#111111",
              border: "1px solid rgba(0,0,0,0.08)",
              "& .MuiTypography-root": { color: "#111111" },
              "& .MuiListItemText-primary": { color: "#111111" }
            }}
          >
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 1 }}>
              {texts.processBoardTitle}
            </Typography>
            <Typography variant="body2" sx={{ mb: 0.5 }}>
              {texts.overallProcess}: … {processTree.overallProgress}%
            </Typography>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, Math.max(0, processTree.overallProgress))}
              sx={{
                height: 10,
                borderRadius: 1,
                bgcolor: "rgba(0,0,0,0.08)",
                "& .MuiLinearProgress-bar": { bgcolor: ACCENT, borderRadius: 1 }
              }}
            />
            <Stack direction="row" spacing={1} sx={{ mt: 2, mb: 2 }}>
              <Button
                fullWidth
                variant="contained"
                startIcon={processTree.runState === "running" ? <PauseIcon /> : <PlayArrowIcon />}
                onClick={() =>
                  processTree.runState === "running" ? sendProcessControl("pause") : sendProcessControl("resume")
                }
                disabled={!processTree.controlEnabled}
                sx={{
                  bgcolor: ACCENT,
                  color: "#fff",
                  py: 1.25,
                  fontWeight: 700,
                  "&:hover": { bgcolor: "#659a28" },
                  "&.Mui-disabled": { bgcolor: "rgba(0,0,0,0.12)", color: "rgba(0,0,0,0.26)" }
                }}
              >
                {processTree.runState === "running" ? texts.btnPause : texts.btnResume}
              </Button>
              <Button
                fullWidth
                variant="outlined"
                startIcon={<StopIcon />}
                onClick={() => sendProcessControl("stop")}
                disabled={!processTree.controlEnabled}
                sx={{
                  borderColor: ACCENT,
                  color: "#111",
                  py: 1.25,
                  fontWeight: 700,
                  "&:hover": { borderColor: "#659a28", bgcolor: "rgba(118,184,45,0.08)" }
                }}
            >
              {texts.btnStop}
            </Button>
            </Stack>
          <Typography variant="caption" sx={{ display: "block", mb: 1, color: "rgba(0,0,0,0.55)" }}>
            {processTree.runState === "waiting"
              ? texts.statusWaiting
              : processTree.runState === "ready"
                ? texts.statusReady
                : processTree.runState === "running"
                  ? texts.statusRunning
                  : processTree.runState === "paused"
                    ? texts.statusPaused
                    : texts.statusIdle}
          </Typography>
            <Divider sx={{ my: 1, borderColor: "rgba(0,0,0,0.08)" }} />
            <Box sx={{ maxHeight: 360, overflowY: "auto", pr: 0.5 }}>
            <List dense disablePadding>
              {processTree.tasks.map((task) => (
                <Box key={task.id} sx={{ mb: 1.5 }}>
                  <Typography variant="subtitle2" sx={{ fontWeight: 700, pl: 0.5 }}>
                    {getLocalizedTaskTitle(task.id, task.title)}
                  </Typography>
                  <List component="div" disablePadding>
                    {(task.children || []).map((child) => {
                      const p = Math.min(100, Math.max(0, Number(child.progress) || 0));
                      const done = p >= 100;
                      const selected = selectedSubId === child.id;
                      return (
                        <ListItem key={child.id} disablePadding sx={{ display: "block" }}>
                          <ListItemButton
                            onClick={() => setSelectedSubId(child.id)}
                            sx={{
                              borderRadius: 1,
                              alignItems: "flex-start",
                              borderLeft: selected ? `4px solid ${ACCENT}` : "4px solid transparent",
                              bgcolor: selected ? "rgba(118,184,45,0.1)" : "transparent",
                              py: 1,
                              "&:hover": { bgcolor: selected ? "rgba(118,184,45,0.14)" : "rgba(0,0,0,0.04)" }
                            }}
                          >
                            <ListItemIcon sx={{ minWidth: 36, mt: 0.25 }}>
                              {done ? (
                                <CheckCircleIcon sx={{ color: ACCENT, fontSize: 22 }} />
                              ) : (
                                <Box sx={{ width: 22, height: 22, borderRadius: "50%", border: "2px solid rgba(0,0,0,0.2)" }} />
                              )}
                            </ListItemIcon>
                            <ListItemText
                              primary={
                                <Typography variant="body2" sx={{ fontWeight: done ? 600 : 500 }}>
                                  - {getLocalizedTaskTitle(child.id, child.title)}
                                </Typography>
                              }
                              secondary={
                                <Box sx={{ mt: 0.75, width: "100%" }}>
                                  <LinearProgress
                                    variant="determinate"
                                    value={p}
                                    sx={{
                                      height: 8,
                                      borderRadius: 1,
                                      bgcolor: "rgba(0,0,0,0.08)",
                                      "& .MuiLinearProgress-bar": {
                                        bgcolor: done ? ACCENT : "rgba(118,184,45,0.65)",
                                        borderRadius: 1
                                      }
                                    }}
                                  />
                                  <Typography variant="caption" sx={{ color: "rgba(0,0,0,0.55)" }}>
                                    {p}%
                                  </Typography>
                                </Box>
                              }
                              secondaryTypographyProps={{ component: "div" }}
                            />
                          </ListItemButton>
                        </ListItem>
                      );
                    })}
                  </List>
                </Box>
              ))}
            </List>
          </Box>
          <Divider sx={{ my: 1, borderColor: "rgba(0,0,0,0.08)" }} />
          <Typography variant="caption" sx={{ color: "rgba(0,0,0,0.55)" }}>
            連線與事件紀錄
          </Typography>
          {renderLogs(processLogs, "process")}
          </Paper>

          <Paper sx={{ p: 2, flex: 1, minHeight: "70vh" }}>
            <Typography variant="h6">{texts.displayBoardTitle}</Typography>
            <Tabs value={activeView} onChange={(_, v) => switchView(v)} sx={{ mb: 1 }}>
            <Tab value="digital" label={texts.tabDigital} />
            <Tab value="camera" label={texts.tabCamera} />
            <Tab value="robot_status" label={texts.tabRobotStatus} />
            </Tabs>
            {(activeView === "digital" || activeView === "camera") && (
              <Box sx={{ width: "100%", aspectRatio: "16/9", bgcolor: "#000", borderRadius: 1, overflow: "hidden", display: "flex", justifyContent: "center", alignItems: "center" }}>
                <img
                  src={activeView === "digital" ? digitalImage : cameraImage}
                  alt="stream"
                  style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
                />
              </Box>
            )}
            {activeView === "robot_status" && (
              <List dense sx={{ maxHeight: 300, overflowY: "auto" }}>
              {Math.max(robotJointNames.length, robotJointAngles.length) === 0 ? (
                <ListItem>
                  <ListItemText primary={texts.robotStatusNone} />
                </ListItem>
                ) : (
                  Array.from(
                    { length: Math.max(robotJointNames.length, robotJointAngles.length) },
                    (_, i) => (
                    <ListItem key={`${robotJointNames[i] || "joint"}-${i}`}>
                      <ListItemText
                        primary={`${robotJointNames[i] || `joint_${i}`}: ${(Number(robotJointAngles[i]) || 0).toFixed(3)}`}
                      />
                    </ListItem>
                  ))
                )}
              </List>
            )}
            {renderLogs(displayLogs, "display")}
          </Paper>

          <Paper sx={{ p: 2, flex: 1, minHeight: "70vh", display: "flex", flexDirection: "column" }}>
            <Typography variant="h6">{texts.commandBoardTitle}</Typography>
            <Divider sx={{ my: 1 }} />
            <Stack spacing={1} sx={{ flex: 1, overflowY: "auto", mb: 1 }}>
              {chatMessages.map((msg, idx) => (
                <Box
                  key={idx}
                  sx={{
                    alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                    maxWidth: "80%",
                    bgcolor: msg.role === "user" ? "primary.main" : "grey.800",
                    px: 1.5,
                    py: 1,
                    borderRadius: 2
                  }}
                >
                  <Typography variant="body2">{msg.text}</Typography>
                </Box>
              ))}
            </Stack>
            <TextField
              fullWidth
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
            placeholder={texts.commandPlaceholder}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title={browserSupportsSpeechRecognition ? texts.micToggleLabel : texts.micNotSupported}>
                      <span>
                        <IconButton
                          disabled={!browserSupportsSpeechRecognition}
                          onClick={() => void handleMicToggle()}
                          sx={{
                            borderRadius: "50%",
                            bgcolor: micOn && micSound ? ACCENT : "transparent",
                            color:
                              micOn && micSound ? "#fff" : micOn ? "primary.main" : "action.disabled",
                            transition: "background-color 0.06s ease",
                            "&:hover": {
                              bgcolor: micOn && micSound ? "#659a28" : "action.hover"
                            },
                            "&.Mui-disabled": { opacity: 0.45 }
                          }}
                        >
                          {micOn ? <MicIcon /> : <MicOffIcon />}
                        </IconButton>
                      </span>
                    </Tooltip>
                    <IconButton onClick={sendCommand}>
                      <SendIcon />
                    </IconButton>
                  </InputAdornment>
                )
              }}
            />
            {renderLogs(commandLogs, "command")}
          </Paper>
        </Stack>
      </Box>

      {scrollMaxY > 0 && (
        <Box
          sx={{
            position: "absolute",
            right: 10,
            top: "50%",
            height: "70%",
            transform: "translateY(-50%)",
            display: "flex",
            alignItems: "center",
            pointerEvents: "auto",
            bgcolor: "rgba(255,255,255,0.35)",
            borderRadius: 2,
            px: 0.5
          }}
        >
          <Slider
            orientation="vertical"
            min={0}
            max={100}
            value={scrollSliderValue}
            onChange={handlePageScrollSlider}
          />
        </Box>
      )}
    </Box>
  );
}
