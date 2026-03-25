export const Role = {
  FRONTEND: "frontend",
  ACTPLAN: "worker_actplan",
  VISION: "worker_vision",
  ROBOT: "worker_robot"
};

export const Event = {
  REGISTER: "register",
  REGISTER_ACK: "register_ack",
  ERROR: "error",
  HEARTBEAT: "heartbeat",
  TASK_STATUS: "task_status",
  LOG: "log",
  COMMAND_INPUT: "command_input",
  COMMAND_REPLY: "command_reply",
  SUBSCRIBE_VIEW: "subscribe_view",
  UNSUBSCRIBE_VIEW: "unsubscribe_view",
  VIEW_STATUS: "view_status",
  FRAME: "frame",
  ROBOT_STATUS_INIT: "robot_status_init",
  ROBOT_STATUS_UPDATE: "robot_status_update",
  PROCESS_SNAPSHOT: "process_snapshot",
  PROCESS_CONTROL: "process_control"
};
