import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  useReactFlow,
  type IsValidConnection,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type OnSelectionChangeFunc,
  type ReactFlowInstance,
  type XYPosition,
} from '@xyflow/react'
import type { FlowEdge, FlowNode } from '../../types/workflow'
import WorkflowNode from './WorkflowNode'
import { CATEGORY_PRESENTATION, FLOWPILOT_NODE_MIME, nodeCategory } from './nodePresentation'

const nodeTypes = { flowpilotNode: WorkflowNode }
const defaultEdgeOptions = { type: 'smoothstep', style: { stroke: '#78899d', strokeWidth: 1.8 } }

export interface WorkflowCanvasProps {
  nodes: FlowNode[]
  edges: FlowEdge[]
  onNodesChange: OnNodesChange<FlowNode>
  onEdgesChange: OnEdgesChange<FlowEdge>
  onConnect: OnConnect
  isValidConnection: IsValidConnection<FlowEdge>
  onSelectionChange: OnSelectionChangeFunc<FlowNode, FlowEdge>
  onDropNode: (type: string, position: XYPosition) => void
  onInit?: (instance: ReactFlowInstance<FlowNode, FlowEdge>) => void
}

export default function WorkflowCanvas({ onDropNode, ...props }: WorkflowCanvasProps) {
  const { screenToFlowPosition } = useReactFlow<FlowNode, FlowEdge>()
  return (
    <section className="canvas-shell" aria-label="Workflow canvas"
      onDragOver={(event) => {
        if (!event.dataTransfer.types.includes(FLOWPILOT_NODE_MIME)) return
        event.preventDefault()
        event.dataTransfer.dropEffect = 'copy'
      }}
      onDrop={(event) => {
        event.preventDefault()
        const type = event.dataTransfer.getData(FLOWPILOT_NODE_MIME)
        if (!type) return
        onDropNode(type, screenToFlowPosition({ x: event.clientX, y: event.clientY }))
      }}>
      <ReactFlow<FlowNode, FlowEdge> {...props}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        colorMode="dark"
        fitView={false}
        minZoom={0.15}
        maxZoom={2.5}
        deleteKeyCode={['Backspace', 'Delete']}
        snapToGrid
        snapGrid={[16, 16]}
        ariaLabelConfig={{ 'controls.fitView.ariaLabel': 'Fit workflow to view' }}>
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#364353" />
        <Controls showInteractive={false} position="bottom-left" />
        <MiniMap<FlowNode> nodeColor={(node) => CATEGORY_PRESENTATION[nodeCategory(node.data.nodeType, node.data.metadata)].color}
          nodeStrokeWidth={2} pannable zoomable position="bottom-right" ariaLabel="Workflow minimap" />
      </ReactFlow>
      {props.nodes.length === 0 && <div className="canvas-empty" aria-hidden="true">
        <span className="canvas-empty-symbol">+</span>
        <h2>Start with a trigger.</h2>
        <p>Drag a node from the library to begin your workflow.</p>
        <span>Connect nodes to give your ideas a direction.</span>
      </div>}
    </section>
  )
}
