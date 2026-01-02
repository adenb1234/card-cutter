#!/usr/bin/env python3
"""
Card Cutter Web Interface
Flask app for the debate research tool.
"""

import os
import json
import uuid
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv

load_dotenv()

from search import (
    search_pipeline,
    cut_card,
    SearchResult,
    Card,
)

app = Flask(__name__)

# Store results in memory (for MVP - would use database in production)
search_cache = {}
card_cache = {}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search():
    """Run the search pipeline and return results."""
    data = request.json
    query = data.get('query', '')
    start_date = data.get('start_date')
    num_queries = data.get('num_queries', 4)
    results_per_query = data.get('results_per_query', 8)

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    try:
        results = search_pipeline(
            query,
            start_date=start_date,
            num_queries=num_queries,
            results_per_query=results_per_query,
            fetch_full_text=True,
        )

        # Cache results with a session ID
        session_id = str(uuid.uuid4())
        search_cache[session_id] = {
            'query': query,
            'results': results,
        }

        # Format results for JSON response
        results_json = []
        for i, r in enumerate(results):
            results_json.append({
                'index': i,
                'title': r.title,
                'url': r.url,
                'published_date': r.published_date[:10] if r.published_date else None,
                'score': r.score,
                'preview': r.full_text[:500] + '...' if r.full_text and len(r.full_text) > 500 else r.full_text,
                'full_text_length': len(r.full_text) if r.full_text else 0,
            })

        return jsonify({
            'session_id': session_id,
            'query': query,
            'count': len(results),
            'results': results_json,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cut', methods=['POST'])
def cut():
    """Cut a card from a search result."""
    data = request.json
    session_id = data.get('session_id')
    result_index = data.get('result_index', 0)
    highlight_level = data.get('highlight_level', 'moderate')

    if not session_id or session_id not in search_cache:
        return jsonify({'error': 'Invalid session. Please search again.'}), 400

    session = search_cache[session_id]
    results = session['results']
    query = session['query']

    if result_index < 0 or result_index >= len(results):
        return jsonify({'error': 'Invalid result index'}), 400

    try:
        result = results[result_index]
        card = cut_card(result, query, highlight_level=highlight_level)

        # Cache the card
        card_id = str(uuid.uuid4())
        card_cache[card_id] = card

        # Build HTML-formatted body
        formatted_body = format_card_body_html(card)

        return jsonify({
            'card_id': card_id,
            'tag': card.tag,
            'author_name': card.author_name,
            'author_year': card.author_year,
            'author_quals': card.author_quals,
            'article_title': card.article_title,
            'url': card.url,
            'body_html': formatted_body,
            'body_plain': card.body,
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


def format_card_body_html(card: Card) -> str:
    """Format card body as HTML with highlighting and underlining."""
    # Build character-level format map
    char_format = ['small'] * len(card.body)
    sorted_markup = sorted(card.markup, key=lambda x: x[0])

    for start, end, level in sorted_markup:
        for i in range(start, min(end, len(card.body))):
            if level == 'highlight':
                char_format[i] = 'highlight'
            elif level == 'underline' and char_format[i] != 'highlight':
                char_format[i] = 'underline'

    # Build HTML
    result = []
    current_format = None

    for i, char in enumerate(card.body):
        fmt = char_format[i]
        if fmt != current_format:
            # Close previous tag
            if current_format == 'highlight':
                result.append('</span>')
            elif current_format == 'underline':
                result.append('</span>')
            elif current_format == 'small':
                result.append('</span>')

            # Open new tag
            if fmt == 'highlight':
                result.append('<span class="highlight">')
            elif fmt == 'underline':
                result.append('<span class="underline">')
            elif fmt == 'small':
                result.append('<span class="small">')

            current_format = fmt

        # Escape HTML chars
        if char == '<':
            result.append('&lt;')
        elif char == '>':
            result.append('&gt;')
        elif char == '&':
            result.append('&amp;')
        elif char == '\n':
            result.append('<br>')
        else:
            result.append(char)

    # Close final tag
    if current_format:
        result.append('</span>')

    return ''.join(result)


@app.route('/download/<card_id>')
def download(card_id):
    """Download card as Word document."""
    if card_id not in card_cache:
        return jsonify({'error': 'Card not found'}), 404

    card = card_cache[card_id]

    # Generate filename
    filename = f"card_{card.author_name}_{card.author_year}.docx"
    filepath = f"/tmp/{card_id}.docx"

    card.save_to_docx(filepath)

    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


if __name__ == '__main__':
    app.run(debug=True, port=5000, host='0.0.0.0')
