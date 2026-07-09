"""
document_ingest.py — Document Ingestion for HR Policies

Handles ingestion of HR policies from various document formats:
- PDF files
- Word documents (DOCX)
- Text files (TXT, MD)
- Images (with OCR)

Automatically extracts text, chunks it, creates embeddings, and stores in vector DB.
"""

import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib

from app.vector_db import store_policy_document, embed_text

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_FORMATS = {
    ".pdf": "extract_pdf",
    ".docx": "extract_docx",
    ".doc": "extract_docx",
    ".txt": "extract_text",
    ".md": "extract_text",
}

# Configuration
MAX_CHUNK_SIZE = 1000  # Characters per chunk
CHUNK_OVERLAP = 200    # Overlap between chunks


def extract_pdf(file_path: str) -> str:
    """
    Extract text from PDF file.
    
    Args:
        file_path: Path to PDF file
    
    Returns:
        Extracted text content
    """
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(file_path)
        logger.info(f"Extracted {len(text)} characters from PDF: {file_path}")
        return text
    except Exception as e:
        logger.error(f"Error extracting PDF {file_path}: {e}")
        return ""


def extract_docx(file_path: str) -> str:
    """
    Extract text from Word document (DOCX/DOC).
    
    Args:
        file_path: Path to DOCX/DOC file
    
    Returns:
        Extracted text content
    """
    try:
        from docx import Document
        doc = Document(file_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        logger.info(f"Extracted {len(text)} characters from DOCX: {file_path}")
        return text
    except Exception as e:
        logger.error(f"Error extracting DOCX {file_path}: {e}")
        return ""


def extract_text(file_path: str) -> str:
    """
    Extract text from plain text file.
    
    Args:
        file_path: Path to TXT/MD file
    
    Returns:
        File content
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
        logger.info(f"Extracted {len(text)} characters from TXT: {file_path}")
        return text
    except Exception as e:
        logger.error(f"Error extracting TXT {file_path}: {e}")
        return ""


def extract_image(file_path: str) -> str:
    """
    Extract text from image using OCR (if available).
    
    Args:
        file_path: Path to image file
    
    Returns:
        Extracted text content
    """
    try:
        import pytesseract
        from PIL import Image
        
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        logger.info(f"Extracted {len(text)} characters from image: {file_path}")
        return text
    except ImportError:
        logger.warning("pytesseract not installed. Image OCR not available. Install with: pip install pytesseract pillow")
        return ""
    except Exception as e:
        logger.error(f"Error extracting image {file_path}: {e}")
        return ""


def chunk_text(text: str, chunk_size: int = MAX_CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """
    Split text into overlapping chunks.
    
    Args:
        text: Text to chunk
        chunk_size: Size of each chunk in characters
        overlap: Number of characters to overlap between chunks
    
    Returns:
        List of text chunks
    """
    if not text or len(text) < chunk_size:
        return [text] if text else []
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        
        # Find sentence boundary for cleaner chunks
        if end < len(text):
            last_period = chunk.rfind('.')
            last_newline = chunk.rfind('\n')
            split_pos = max(last_period, last_newline)
            
            if split_pos > chunk_size * 0.7:  # Only use if reasonable
                end = start + split_pos + 1
        
        chunks.append(text[start:end].strip())
        start = end - overlap
    
    logger.info(f"Split text into {len(chunks)} chunks")
    return chunks


def generate_doc_id(file_name: str, chunk_index: int = 0) -> str:
    """Generate unique document ID from file name and chunk index."""
    base_name = Path(file_name).stem
    hash_suffix = hashlib.md5(file_name.encode()).hexdigest()[:8]
    return f"doc_{base_name}_{chunk_index}_{hash_suffix}".replace(" ", "_").lower()


def ingest_document(
    file_path: str,
    policy_type: str,
    section: str = "General",
    metadata: Optional[Dict[str, Any]] = None,
    chunk_size: int = MAX_CHUNK_SIZE
) -> Dict[str, Any]:
    """
    Ingest a single document into vector database.
    
    Args:
        file_path: Path to document file
        policy_type: Type of policy (e.g., "leave_policy", "salary_policy")
        section: Policy section name
        metadata: Additional metadata
        chunk_size: Size of text chunks
    
    Returns:
        Dictionary with ingestion results
    """
    results = {
        "file": os.path.basename(file_path),
        "success": False,
        "chunks_processed": 0,
        "chunks_stored": 0,
        "error": None
    }
    
    try:
        # Check file exists
        if not os.path.exists(file_path):
            results["error"] = f"File not found: {file_path}"
            logger.error(results["error"])
            return results
        
        # Get file extension
        file_ext = Path(file_path).suffix.lower()
        if file_ext not in SUPPORTED_FORMATS:
            results["error"] = f"Unsupported format: {file_ext}. Supported: {list(SUPPORTED_FORMATS.keys())}"
            logger.error(results["error"])
            return results
        
        # Extract text based on format
        logger.info(f"Ingesting document: {file_path}")
        extract_func_name = SUPPORTED_FORMATS[file_ext]
        
        if extract_func_name == "extract_pdf":
            text = extract_pdf(file_path)
        elif extract_func_name == "extract_docx":
            text = extract_docx(file_path)
        elif extract_func_name == "extract_text":
            text = extract_text(file_path)
        else:
            text = ""
        
        if not text or len(text.strip()) < 10:
            results["error"] = "No text could be extracted from document"
            logger.warning(results["error"])
            return results
        
        # Clean text
        text = " ".join(text.split())  # Normalize whitespace
        
        # Chunk text
        chunks = chunk_text(text, chunk_size)
        results["chunks_processed"] = len(chunks)
        
        # Store each chunk
        for chunk_idx, chunk in enumerate(chunks):
            try:
                doc_id = generate_doc_id(file_path, chunk_idx)
                
                # Prepare metadata
                chunk_metadata = {
                    "file_name": os.path.basename(file_path),
                    "file_path": file_path,
                    "chunk_index": chunk_idx,
                    "chunk_total": len(chunks),
                    "file_size": os.path.getsize(file_path),
                    **(metadata or {})
                }
                
                # Store in vector DB
                success = store_policy_document(
                    doc_id=doc_id,
                    section=section,
                    policy_type=policy_type,
                    content=chunk,
                    metadata=chunk_metadata
                )
                
                if success:
                    results["chunks_stored"] += 1
                else:
                    logger.warning(f"Failed to store chunk {chunk_idx} from {file_path}")
            
            except Exception as e:
                logger.error(f"Error storing chunk {chunk_idx}: {e}")
                continue
        
        if results["chunks_stored"] > 0:
            results["success"] = True
            logger.info(f"Successfully ingested {results['chunks_stored']}/{results['chunks_processed']} chunks from {file_path}")
        else:
            results["error"] = "Failed to store any chunks"
        
        return results
    
    except Exception as e:
        results["error"] = str(e)
        logger.error(f"Error ingesting document {file_path}: {e}")
        return results


def ingest_directory(
    directory_path: str,
    policy_type: str,
    section: str = "General",
    recursive: bool = True,
    metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Ingest all supported documents from a directory.
    
    Args:
        directory_path: Path to directory containing documents
        policy_type: Type of policy
        section: Policy section name
        recursive: Whether to search subdirectories
        metadata: Additional metadata for all documents
    
    Returns:
        List of ingestion results for each file
    """
    results = []
    
    if not os.path.isdir(directory_path):
        logger.error(f"Directory not found: {directory_path}")
        return results
    
    # Find all supported files
    pattern = "**/*" if recursive else "*"
    search_path = Path(directory_path)
    
    files_found = []
    for ext in SUPPORTED_FORMATS.keys():
        files_found.extend(search_path.glob(f"{pattern}{ext}"))
    
    logger.info(f"Found {len(files_found)} documents in {directory_path}")
    
    # Ingest each file
    for file_path in files_found:
        result = ingest_document(
            str(file_path),
            policy_type=policy_type,
            section=section,
            metadata=metadata
        )
        results.append(result)
    
    # Summary
    successful = sum(1 for r in results if r["success"])
    total_chunks = sum(r["chunks_stored"] for r in results)
    logger.info(f"Ingestion complete: {successful}/{len(results)} files, {total_chunks} chunks stored")
    
    return results


def batch_ingest(
    files: List[str],
    policy_type: str,
    section: str = "General"
) -> Dict[str, Any]:
    """
    Ingest multiple files as a batch.
    
    Args:
        files: List of file paths
        policy_type: Type of policy
        section: Policy section
    
    Returns:
        Summary of batch ingestion
    """
    results = []
    
    for file_path in files:
        result = ingest_document(
            file_path=file_path,
            policy_type=policy_type,
            section=section
        )
        results.append(result)
    
    return {
        "total_files": len(files),
        "successful_files": sum(1 for r in results if r["success"]),
        "total_chunks_stored": sum(r["chunks_stored"] for r in results),
        "results": results
    }


def validate_document(file_path: str) -> Dict[str, Any]:
    """
    Validate that a document can be processed.
    
    Args:
        file_path: Path to document
    
    Returns:
        Validation result
    """
    result = {
        "file": os.path.basename(file_path),
        "valid": False,
        "format": None,
        "size_kb": 0,
        "issues": []
    }
    
    try:
        if not os.path.exists(file_path):
            result["issues"].append("File does not exist")
            return result
        
        file_ext = Path(file_path).suffix.lower()
        result["format"] = file_ext
        result["size_kb"] = os.path.getsize(file_path) / 1024
        
        if file_ext not in SUPPORTED_FORMATS:
            result["issues"].append(f"Unsupported format. Supported: {list(SUPPORTED_FORMATS.keys())}")
            return result
        
        if result["size_kb"] > 50000:  # 50MB limit
            result["issues"].append(f"File too large: {result['size_kb']:.1f}KB (max 50MB)")
            return result
        
        # Try to extract text
        extract_func_name = SUPPORTED_FORMATS[file_ext]
        if extract_func_name == "extract_pdf":
            text = extract_pdf(file_path)
        elif extract_func_name == "extract_docx":
            text = extract_docx(file_path)
        elif extract_func_name == "extract_text":
            text = extract_text(file_path)
        else:
            text = ""
        
        if not text or len(text.strip()) < 10:
            result["issues"].append("No extractable text found in document")
            return result
        
        result["valid"] = True
        return result
    
    except Exception as e:
        result["issues"].append(f"Error validating: {str(e)}")
        return result
