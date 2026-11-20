import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-cartesian-dist-min";

const Plot = createPlotlyComponent(Plotly);

/** Plotly wrapper with the project's defaults: transparent background, compact margins, no mode bar. */
export default function Chart({ data, layout = {}, height = 320 }) {
  return (
    <Plot
      data={data}
      layout={{
        autosize: true,
        height,
        margin: { t: 30, r: 16, b: 48, l: 56 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        legend: { orientation: "h", y: -0.2 },
        font: { family: "system-ui, sans-serif", size: 12, color: "#334155" },
        ...layout,
      }}
      useResizeHandler
      style={{ width: "100%" }}
      config={{ displayModeBar: false, responsive: true }}
    />
  );
}
