"""
Context retrieval for the workflow engine.

In air-gapped environments, we can't use external embedding APIs.
This module provides lightweight, local context retrieval using:
1. Keyword matching (TF-IDF style)
2. Section headers matching
3. File relevance scoring

For production, consider replacing with local embeddings (sentence-transformers).
"""
import re
from pathlib import Path
from dataclasses import dataclass
from collections import Counter
from typing import Optional


@dataclass
class DocumentChunk:
    """A chunk of a design document."""
    source: str           # Filename
    section: str          # Section header (if any)
    content: str          # The actual text
    score: float = 0.0    # Relevance score


class ContextRetriever:
    """
    Retrieves relevant context from design documents.
    
    Instead of dumping all design docs into the prompt, this retrieves
    only the sections most relevant to the current task.
    """
    
    def __init__(self, design_path: Path, contracts_path: Path):
        self.design_path = design_path
        self.contracts_path = contracts_path
        self.chunks: list[DocumentChunk] = []
        self.loaded = False
        
    def load(self):
        """Load and chunk all design documents."""
        self.chunks = []
        
        # Load design docs
        for doc_file in sorted(self.design_path.glob("*.md")):
            chunks = self._chunk_document(doc_file, prefix="DESIGN")
            self.chunks.extend(chunks)
        
        # Load contracts
        for doc_file in sorted(self.contracts_path.glob("*.md")):
            chunks = self._chunk_document(doc_file, prefix="CONTRACT")
            self.chunks.extend(chunks)
        
        self.loaded = True
        return len(self.chunks)
    
    def _chunk_document(self, path: Path, prefix: str = "") -> list[DocumentChunk]:
        """Split a document into chunks by section headers."""
        with open(path) as f:
            content = f.read()
        
        chunks = []
        filename = path.stem
        
        # Split by markdown headers (## or ###)
        sections = re.split(r'\n(?=#{1,3}\s)', content)
        
        for section in sections:
            if not section.strip():
                continue
            
            # Extract section header
            header_match = re.match(r'^(#{1,3})\s*(.+?)(?:\n|$)', section)
            if header_match:
                section_name = header_match.group(2).strip()
            else:
                section_name = "Introduction"
            
            chunks.append(DocumentChunk(
                source=f"{prefix}: {filename}",
                section=section_name,
                content=section.strip(),
            ))
        
        # If no sections found, treat whole doc as one chunk
        if not chunks:
            chunks.append(DocumentChunk(
                source=f"{prefix}: {filename}",
                section="Full Document",
                content=content.strip(),
            ))
        
        return chunks
    
    def retrieve(self, query: str, max_chunks: int = 10, 
                 max_tokens: int = 8000) -> list[DocumentChunk]:
        """
        Retrieve the most relevant chunks for a query.
        
        Args:
            query: The task description or keywords
            max_chunks: Maximum number of chunks to return
            max_tokens: Approximate token limit (chars / 4)
        
        Returns:
            List of relevant DocumentChunks, sorted by relevance
        """
        if not self.loaded:
            self.load()
        
        if not self.chunks:
            return []
        
        # Score each chunk
        query_terms = self._extract_terms(query)
        
        for chunk in self.chunks:
            chunk.score = self._score_chunk(chunk, query_terms)
        
        # Sort by score descending
        ranked = sorted(self.chunks, key=lambda c: c.score, reverse=True)
        
        # Select chunks within token budget
        selected = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough token-to-char ratio
        
        for chunk in ranked[:max_chunks * 2]:  # Consider more than max
            if chunk.score <= 0:
                continue
            
            chunk_chars = len(chunk.content)
            if total_chars + chunk_chars > char_limit:
                continue
            
            selected.append(chunk)
            total_chars += chunk_chars
            
            if len(selected) >= max_chunks:
                break
        
        return selected
    
    def retrieve_for_task(self, task) -> Optional[str]:
        """
        Retrieve relevant context for a task.
        
        Builds a query from task attributes and returns formatted context.
        """
        # Build query from task
        query_parts = [task.title, task.description]
        
        if task.prompt:
            query_parts.append(task.prompt[:500])  # First part of prompt
        
        if task.input_contract:
            query_parts.append(task.input_contract)
        
        if task.output_contract:
            query_parts.append(task.output_contract)
        
        for criterion in task.acceptance_criteria:
            query_parts.append(criterion)
        
        query = " ".join(query_parts)
        
        # Retrieve relevant chunks
        chunks = self.retrieve(query, max_chunks=15, max_tokens=12000)
        
        if not chunks:
            return None
        
        # Format as context
        context_parts = []
        current_source = None
        
        for chunk in chunks:
            if chunk.source != current_source:
                if current_source:
                    context_parts.append("\n---\n")
                context_parts.append(f"## {chunk.source}\n")
                current_source = chunk.source
            
            context_parts.append(f"\n### {chunk.section}\n")
            context_parts.append(chunk.content)
        
        return "\n".join(context_parts)
    
    def get_full_context(self) -> Optional[str]:
        """
        Get all design context (for small document sets).
        
        Use this when total docs < 10K tokens, otherwise use retrieve().
        """
        if not self.loaded:
            self.load()
        
        if not self.chunks:
            return None
        
        # Group by source
        by_source = {}
        for chunk in self.chunks:
            if chunk.source not in by_source:
                by_source[chunk.source] = []
            by_source[chunk.source].append(chunk)
        
        # Format
        parts = []
        for source, chunks in by_source.items():
            parts.append(f"## {source}\n")
            for chunk in chunks:
                parts.append(f"### {chunk.section}\n")
                parts.append(chunk.content)
                parts.append("\n")
            parts.append("\n---\n")
        
        return "\n".join(parts)
    
    def _extract_terms(self, text: str) -> Counter:
        """Extract weighted terms from text."""
        # Normalize
        text = text.lower()
        
        # Extract words
        words = re.findall(r'\b[a-z][a-z0-9_]+\b', text)
        
        # Filter stopwords
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
            'for', 'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are',
            'were', 'been', 'be', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'could', 'should', 'may', 'might', 'must',
            'this', 'that', 'these', 'those', 'it', 'its', 'they', 'them',
            'we', 'you', 'your', 'our', 'their', 'what', 'which', 'who',
            'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
            'few', 'more', 'most', 'other', 'some', 'such', 'no', 'not',
            'only', 'own', 'same', 'so', 'than', 'too', 'very', 'can',
            'just', 'should', 'now', 'also', 'use', 'using', 'used',
        }
        
        terms = [w for w in words if w not in stopwords and len(w) > 2]
        return Counter(terms)
    
    def _score_chunk(self, chunk: DocumentChunk, query_terms: Counter) -> float:
        """Score a chunk's relevance to query terms."""
        chunk_text = f"{chunk.section} {chunk.content}".lower()
        chunk_terms = self._extract_terms(chunk_text)
        
        if not chunk_terms or not query_terms:
            return 0.0
        
        # Calculate overlap
        score = 0.0
        
        for term, query_count in query_terms.items():
            if term in chunk_terms:
                # TF-IDF-like scoring
                tf = chunk_terms[term] / sum(chunk_terms.values())
                score += tf * query_count
        
        # Boost for exact phrase matches in section header
        section_lower = chunk.section.lower()
        for term in query_terms:
            if term in section_lower:
                score *= 1.5
        
        # Boost for contract documents when task has contracts
        if "CONTRACT" in chunk.source:
            score *= 1.2
        
        return score


# Singleton for easy access
_retriever: Optional[ContextRetriever] = None


def get_retriever(design_path: Path, contracts_path: Path) -> ContextRetriever:
    """Get or create the context retriever singleton."""
    global _retriever
    if _retriever is None:
        _retriever = ContextRetriever(design_path, contracts_path)
    return _retriever
