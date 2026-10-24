import {
  RiLineChartLine,
  RiFileList3Line,
  RiFlaskLine,
  RiShieldCheckLine,
} from "@remixicon/react";
import type { View } from "../WorkspaceShell";

export const sourceApps: {
  view: View;
  name: string;
  system: string;
  icon: typeof RiLineChartLine;
}[] = [
  {
    view: "historian",
    name: "PlantView",
    system: "Historian",
    icon: RiLineChartLine,
  },
  { view: "lims", name: "LabWare", system: "LIMS", icon: RiFlaskLine },
  { view: "mes", name: "Syncade", system: "MES", icon: RiFileList3Line },
  { view: "qms", name: "QualityTrack", system: "QMS", icon: RiShieldCheckLine },
];
