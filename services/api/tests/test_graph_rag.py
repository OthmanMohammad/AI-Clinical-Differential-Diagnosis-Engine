"""Tests for context builder and graph serialization."""

from __future__ import annotations

from app.core.context_builder import serialize_subgraph


class TestSerializeSubgraph:
    def test_serializes_nodes(self, sample_graph_nodes, sample_graph_edges):
        text = serialize_subgraph(sample_graph_nodes, sample_graph_edges)
        assert "Systemic Lupus Erythematosus" in text
        assert "[Disease]" in text
        assert "[Symptom]" in text
        assert "[Gene]" in text

    def test_serializes_relationships(self, sample_graph_nodes, sample_graph_edges):
        text = serialize_subgraph(sample_graph_nodes, sample_graph_edges)
        assert "disease_phenotype_positive" in text
        assert "--[" in text
        assert "]-->" in text

    def test_empty_graph(self):
        text = serialize_subgraph([], [])
        assert "KNOWLEDGE GRAPH CONTEXT" in text
        assert "Entities:" in text

    def test_nodes_without_relationships(self, sample_graph_nodes):
        text = serialize_subgraph(sample_graph_nodes, [])
        assert "Systemic Lupus Erythematosus" in text
        assert "Relationships:" in text
