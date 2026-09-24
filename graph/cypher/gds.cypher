// Project an undirected logistics graph for GDS.
// Edge weight mixes cost, transit time, and predicted risk (higher = worse).
CALL gds.graph.drop('logistics', false);

CALL gds.graph.project(
  'logistics',
  'Location',
  {
    ROUTE: {
      orientation: 'UNDIRECTED',
      properties: ['distance_km', 'cost_usd', 'historical_delay_hours', 'predicted_risk', 'gds_weight', 'baseline_weight']
    }
  }
);

CALL gds.betweenness.write('logistics', {
  writeProperty: 'betweenness'
});

// Example weighted Dijkstra (source substituted by seed/backend).
// CALL gds.shortestPath.dijkstra.stream('logistics', {
//   sourceNode: $source,
//   targetNode: $target,
//   relationshipWeightProperty: 'gds_weight'
// });
