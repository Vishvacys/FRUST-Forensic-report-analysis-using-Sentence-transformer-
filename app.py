from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import os
import json
import pandas as pd
from datetime import datetime
import uuid
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ufdr_analysis.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Initialize extensions
from models import db
db.init_app(app)
CORS(app)

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('reports', exist_ok=True)

# Import models from models.py
from models import UFDRReport, ChatRecord, CallRecord, ImageRecord, AnalysisResult, AIInsight, ForensicPattern, RiskAssessment, ModelPerformance

# Import services
from services.ai_processor import AIProcessor
from services.advanced_ai_processor import AdvancedAIProcessor
from services.ufdr_parser import UFDRParser
from services.report_generator import ReportGenerator

# Initialize services
ai_processor = AIProcessor()
advanced_ai_processor = AdvancedAIProcessor()
ufdr_parser = UFDRParser()
report_generator = ReportGenerator()

@app.route('/api/save-case', methods=['POST'])
def save_case():
    """Save notes/metadata for a case (lightweight bookmark)"""
    try:
        data = request.get_json()
        case_id = data.get('case_id')
        notes = data.get('notes', '').strip()

        if not case_id:
            return jsonify({'error': 'case_id is required'}), 400

        report = db.session.get(UFDRReport, case_id)
        if not report:
            return jsonify({'error': 'Case not found'}), 404

        # Persist notes as a lightweight AnalysisResult entry tagged as 'notes'
        note_record = AnalysisResult(
            report_id=case_id,
            query='[SAVED NOTE]',
            query_type='notes',
            results=json.dumps([]),
            ai_analysis=json.dumps({'notes': notes}),
            insights=json.dumps([notes] if notes else []),
            confidence_score=1.0,
            processing_method='manual',
            timestamp=datetime.utcnow()
        )
        db.session.add(note_record)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Case saved successfully', 'note_id': note_record.id})

    except Exception as e:
        logger.error(f"Error saving case: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Simple health check endpoint for frontend connectivity tests"""
    try:
        return jsonify({
            'ok': True,
            'service': 'ufdr-analysis-backend',
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/')
def welcome():
    """Welcome page - landing page with features"""
    return render_template('welcome.html')

@app.route('/login')
def login():
    """Login page"""
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    """Main dashboard page - requires authentication"""
    return render_template('dashboard.html')

@app.route('/api/check-auth')
def check_auth():
    """Check if user is authenticated"""
    # In a real application, you would check session/token
    # For demo purposes, we'll return success
    return jsonify({'authenticated': True})

@app.route('/cases')
def cases():
    """Cases management page"""
    return render_template('cases.html')

@app.route('/upload', methods=['POST'])
def upload_ufdr():
    """Upload and process UFDR file"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get case information from form data
        case_number = request.form.get('case_number', '').strip()
        case_title = request.form.get('case_title', '').strip()
        investigating_officer = request.form.get('investigating_officer', '').strip()
        
        if not case_number:
            return jsonify({'error': 'Case number is required'}), 400
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Parse UFDR file
            ufdr_data = ufdr_parser.parse_file(filepath)
            
            # Create database record
            report = UFDRReport(
                case_number=case_number,
                case_title=case_title,
                investigating_officer=investigating_officer,
                filename=filename,
                filepath=filepath,
                upload_date=datetime.utcnow(),
                status='processing'
            )
            db.session.add(report)
            db.session.commit()
            
            # Process the data
            process_ufdr_data(report.id, ufdr_data)
            
            return jsonify({
                'success': True,
                'report_id': report.id,
                'case_number': case_number,
                'message': 'UFDR file uploaded and processing started'
            })
        
        return jsonify({'error': 'Invalid file type'}), 400
    
    except Exception as e:
        logger.error(f"Error uploading UFDR: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/query', methods=['POST'])
def process_query():
    """Process natural language query with enhanced AI capabilities"""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        report_id = data.get('report_id')
        use_advanced_ai = data.get('use_advanced_ai', True)  # Default to advanced AI
        
        if not query:
            return jsonify({'error': 'Query cannot be empty'}), 400
        
        if not report_id:
            return jsonify({'error': 'Report ID is required'}), 400
        
        # Get report data
        report = db.session.get(UFDRReport, report_id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        # Gather data from database
        chat_records = ChatRecord.query.filter_by(report_id=report_id).all()
        call_records = CallRecord.query.filter_by(report_id=report_id).all()
        image_records = ImageRecord.query.filter_by(report_id=report_id).all()
        
        # Convert to dictionaries
        query_data = {
            'chats': [chat.to_dict() for chat in chat_records],
            'calls': [call.to_dict() for call in call_records],
            'images': [image.to_dict() for image in image_records]
        }
        
        # Process query with appropriate AI processor
        advanced_results = None
        if use_advanced_ai:
            try:
                advanced_results = advanced_ai_processor.process_query(query, file_id=report_id, data=query_data)
                processing_method = 'advanced_ai'
            except Exception as e:
                logger.warning(f"Advanced AI processing failed, falling back to standard AI: {e}")
                advanced_results = None
                processing_method = 'ai_enhanced'

        # Always run standard AI to obtain concrete result lists compatible with frontend
        standard_results = ai_processor.process_query(query, query_data)
        if not use_advanced_ai:
            processing_method = 'ai_enhanced'
        
        # Extract query type and confidence score
        # Prefer advanced metadata if available, otherwise standard
        base_meta = advanced_results if isinstance(advanced_results, dict) else standard_results
        query_type = base_meta.get('query_type', 'general')
        confidence_score = base_meta.get('confidence_score', 0.0)
        ai_analysis = base_meta.get('ai_analysis', {})
        insights = base_meta.get('insights', [])
        
        # Normalize results shape for frontend and persistence.
        # Priority: advanced_ai filtered_results → standard merged results → raw list
        payload_results = []

        # Try advanced_ai filtered_results first
        if isinstance(advanced_results, dict):
            adv_ai = advanced_results.get('ai_analysis', {})
            adv_data = adv_ai.get('data_analysis', {}).get('filtered_results', {})
            if isinstance(adv_data, dict) and (adv_data.get('chats') or adv_data.get('calls')):
                payload_results = adv_data  # keep as dict; normalized below

        # Fall back to standard_results
        if not payload_results:
            if isinstance(standard_results, dict):
                payload_results = standard_results.get('results', [])
            elif isinstance(standard_results, list):
                payload_results = standard_results

        # If advanced_results has a top-level results list, prefer it if non-empty
        if isinstance(advanced_results, dict):
            adv_payload = advanced_results.get('results')
            if isinstance(adv_payload, list) and adv_payload:
                payload_results = adv_payload

        # Convert dict-of-categories → grouped array for frontend
        if isinstance(payload_results, dict):
            grouped = []
            try:
                chats_list = (payload_results.get('chats')
                              or payload_results.get('chat_messages')
                              or payload_results.get('messages'))
                if isinstance(chats_list, list) and chats_list:
                    grouped.append({'type': 'chat_messages', 'data': chats_list})

                calls_list = (payload_results.get('calls')
                              or payload_results.get('call_records'))
                if isinstance(calls_list, list) and calls_list:
                    grouped.append({'type': 'call_records', 'data': calls_list})

                images_list = (payload_results.get('images')
                               or payload_results.get('media')
                               or payload_results.get('media_files'))
                if isinstance(images_list, list) and images_list:
                    grouped.append({'type': 'media_files', 'data': images_list})

                foreign_calls = payload_results.get('foreign_calls')
                if isinstance(foreign_calls, list) and foreign_calls:
                    grouped.append({'type': 'foreign_calls', 'data': foreign_calls})

                foreign_messages = payload_results.get('foreign_messages')
                if isinstance(foreign_messages, list) and foreign_messages:
                    grouped.append({'type': 'foreign_messages', 'data': foreign_messages})

                foreign_contacts = payload_results.get('foreign_contacts')
                if isinstance(foreign_contacts, list) and foreign_contacts:
                    grouped.append({'type': 'foreign_contacts', 'data': foreign_contacts})
            except Exception:
                grouped = []
            payload_results = grouped

        # Detect multi-intent query and set a clear query_type label
        multi_intent_signals = {
            'drug': ['drug', 'narcotic', 'weed', 'cocaine', 'heroin', 'meth', 'marijuana'],
            'crypto': ['crypto', 'bitcoin', 'btc', 'ethereum', 'wallet', 'blockchain'],
            'foreign': ['foreign', 'international', 'overseas'],
            'weapons': ['weapon', 'gun', 'firearm'],
            'financial': ['launder', 'fraud', 'hawala'],
        }
        q_lower = query.lower()
        active_intents = [label for label, terms in multi_intent_signals.items()
                          if any(t in q_lower for t in terms)]
        if len(active_intents) > 1:
            query_type = 'CHAT MESSAGES'   # multi-category — show unified label
        # else keep query_type from base_meta

        # ── Compute logic-driven risk score (0–100) ───────────────────────────
        risk_score = round(min(confidence_score * 40, 40))  # base from confidence

        # Count flagged records
        total_flagged = 0
        foreign_contact_count = 0
        foreign_call_count = 0

        if isinstance(payload_results, list):
            for grp in payload_results:
                if not isinstance(grp, dict):
                    continue
                gtype = grp.get('type', '')
                gdata = grp.get('data', [])
                count = len(gdata) if isinstance(gdata, list) else 0
                total_flagged += count
                if 'foreign_contact' in gtype:
                    foreign_contact_count += count
                elif 'foreign_call' in gtype:
                    foreign_call_count += count
        elif isinstance(payload_results, dict):
            total_flagged = sum(
                len(v) for v in payload_results.values() if isinstance(v, list)
            )
            foreign_contact_count = len(payload_results.get('foreign_contacts', []))
            foreign_call_count    = len(payload_results.get('foreign_calls', []))

        # Intent-based boosts
        high_risk_intents = {'drug', 'weapons', 'financial'}
        if high_risk_intents & set(active_intents):
            risk_score += 20
        if 'crypto' in active_intents:
            risk_score += 10
        if foreign_contact_count > 0 or foreign_call_count > 0:
            risk_score += 15
        if total_flagged > 10:
            risk_score += 10
        elif total_flagged > 0:
            risk_score += 5

        risk_score = min(int(risk_score), 100)  # cap at 100

        # Derive level label
        if risk_score >= 75:
            risk_level = 'Critical'
        elif risk_score >= 50:
            risk_level = 'High'
        elif risk_score >= 25:
            risk_level = 'Medium'
        else:
            risk_level = 'Low'

        # Update severity on any AI Insights we're about to save
        severity_map = {'Critical': 'critical', 'High': 'high', 'Medium': 'medium', 'Low': 'low'}
        insight_severity = severity_map[risk_level]

        # Save enhanced analysis result
        analysis = AnalysisResult(
            report_id=report_id,
            query=query,
            query_type=query_type,
            results=json.dumps(payload_results),
            ai_analysis=json.dumps(ai_analysis),
            insights=json.dumps(insights),
            confidence_score=confidence_score,
            processing_method=processing_method,
            timestamp=datetime.utcnow()
        )
        db.session.add(analysis)
        db.session.commit()

        # Save AI insights if available
        if insights:
            for insight in insights:
                ai_insight = AIInsight(
                    report_id=report_id,
                    analysis_id=analysis.id,
                    insight_type='general',
                    insight_text=insight,
                    confidence_score=confidence_score,
                    severity_level=insight_severity,
                    timestamp=datetime.utcnow()
                )
                db.session.add(ai_insight)

        # Save forensic patterns if detected
        if ai_analysis.get('patterns'):
            patterns = ai_analysis['patterns']
            for pattern_type, pattern_data in patterns.items():
                if not pattern_data:
                    continue
                items = pattern_data if isinstance(pattern_data, list) else [pattern_data]
                for item in items:
                    if isinstance(item, dict):
                        value = item.get('keyword') or item.get('address') or item.get('pattern_value') or str(item)
                        category = item.get('category', pattern_type)
                    else:
                        value = str(item)
                        category = pattern_type
                    forensic_pattern = ForensicPattern(
                        report_id=report_id,
                        pattern_type=pattern_type,
                        pattern_category=category,
                        pattern_value=value,
                        confidence_score=confidence_score,
                        risk_level=risk_level.lower(),
                        timestamp=datetime.utcnow()
                    )
                    db.session.add(forensic_pattern)

        db.session.commit()

        return jsonify({
            'success': True,
            'results': payload_results,
            'analysis_id': analysis.id,
            'processing_method': processing_method,
            'confidence_score': confidence_score,
            'risk_score': risk_score,
            'risk_level': risk_level,
            'query': query,
        })
    
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/reports')
def list_reports():
    """List all uploaded reports"""
    reports = UFDRReport.query.order_by(UFDRReport.upload_date.desc()).all()
    return jsonify([{
        'id': report.id,
        'case_number': report.case_number,
        'case_title': report.case_title,
        'investigating_officer': report.investigating_officer,
        'filename': report.filename,
        'upload_date': report.upload_date.isoformat(),
        'status': report.status
    } for report in reports])

@app.route('/report/<int:report_id>')
def get_report_details(report_id):
    """Get detailed information about a specific report"""
    report = db.session.get(UFDRReport, report_id)
    if not report:
        return jsonify({'error': 'Report not found'}), 404
    
    # Get related data counts
    chat_count = ChatRecord.query.filter_by(report_id=report_id).count()
    call_count = CallRecord.query.filter_by(report_id=report_id).count()
    image_count = ImageRecord.query.filter_by(report_id=report_id).count()
    
    return jsonify({
        'id': report.id,
        'filename': report.filename,
        'upload_date': report.upload_date.isoformat(),
        'status': report.status,
        'data_summary': {
            'chats': chat_count,
            'calls': call_count,
            'images': image_count
        }
    })

@app.route('/report/<int:report_id>', methods=['DELETE'])
def delete_report(report_id):
    """Delete a specific report and all related records"""
    try:
        report = db.session.get(UFDRReport, report_id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404

        # Attempt to remove associated uploaded file if it still exists
        try:
            if report.filepath and os.path.isfile(report.filepath):
                os.remove(report.filepath)
        except Exception as file_err:
            logger.warning(f"Failed to delete file for report {report_id}: {file_err}")

        # Deleting the report will cascade to child records due to model relationships
        db.session.delete(report)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Report deleted successfully'})
    except Exception as e:
        logger.error(f"Error deleting report {report_id}: {str(e)}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/export/<int:analysis_id>/excel')
def export_analysis_excel(analysis_id):
    """Export analysis results as Excel (.xlsx) report"""
    try:
        analysis = db.session.get(AnalysisResult, analysis_id)
        if not analysis:
            return jsonify({'error': 'Analysis not found'}), 404
        try:
            results  = json.loads(analysis.results)  if analysis.results  else []
            insights = json.loads(analysis.insights) if analysis.insights else []
        except Exception:
            results, insights = [], []
        report_data = report_generator.generate_report(
            file_id=analysis.report_id,
            query=analysis.query,
            results=results,
            insights=insights
        )
        excel_path = report_data.get('excel_path')
        if excel_path and os.path.isfile(excel_path):
            return send_file(
                excel_path,
                as_attachment=True,
                download_name=f'ufdr_analysis_{analysis_id}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        return jsonify({'error': 'Excel report could not be generated'}), 500
    except Exception as e:
        logger.error(f"Error exporting Excel: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/export-analysis-pdf/<int:analysis_id>')
def export_analysis_as_pdf(analysis_id):
    """Generate and serve a PDF for a specific analysis result (called from analysis page)."""
    try:
        analysis = db.session.get(AnalysisResult, analysis_id)
        if not analysis:
            return jsonify({'error': 'Analysis not found'}), 404

        try:
            results  = json.loads(analysis.results)  if analysis.results  else []
            insights = json.loads(analysis.insights) if analysis.insights else []
            ai_data  = json.loads(analysis.ai_analysis) if analysis.ai_analysis else {}
        except Exception:
            results, insights, ai_data = [], [], {}

        # Re-compute risk score from stored data so PDF matches what the UI showed
        multi_intent_signals = {
            'drug': ['drug', 'narcotic', 'weed', 'cocaine', 'heroin', 'meth', 'marijuana'],
            'crypto': ['crypto', 'bitcoin', 'btc', 'ethereum', 'wallet', 'blockchain'],
            'foreign': ['foreign', 'international', 'overseas'],
            'weapons': ['weapon', 'gun', 'firearm'],
            'financial': ['launder', 'fraud', 'hawala'],
        }
        q_lower = (analysis.query or '').lower()
        active_intents = [label for label, terms in multi_intent_signals.items()
                          if any(t in q_lower for t in terms)]

        risk_score = round(min((analysis.confidence_score or 0) * 40, 40))
        high_risk_intents = {'drug', 'weapons', 'financial'}
        if high_risk_intents & set(active_intents):
            risk_score += 20
        if 'crypto' in active_intents:
            risk_score += 10

        total_flagged = 0
        foreign_count = 0
        if isinstance(results, list):
            for grp in results:
                if isinstance(grp, dict):
                    gdata = grp.get('data', [])
                    count = len(gdata) if isinstance(gdata, list) else 0
                    total_flagged += count
                    if 'foreign' in grp.get('type', ''):
                        foreign_count += count
        if foreign_count > 0:
            risk_score += 15
        if total_flagged > 10:
            risk_score += 10
        elif total_flagged > 0:
            risk_score += 5
        risk_score = min(int(risk_score), 100)

        if risk_score >= 75:
            risk_level = 'Critical'
        elif risk_score >= 50:
            risk_level = 'High'
        elif risk_score >= 25:
            risk_level = 'Medium'
        else:
            risk_level = 'Low'

        report_data = report_generator.generate_report(
            file_id=analysis.report_id,
            query=analysis.query,
            results=results,
            insights=insights,
            risk_score=risk_score,
            risk_level=risk_level,
        )

        pdf_path  = report_data.get('pdf_path')
        html_path = report_data.get('html_path')

        if pdf_path and os.path.isfile(pdf_path):
            return send_file(
                pdf_path,
                as_attachment=True,
                download_name=f'fraust_analysis_{analysis_id}.pdf',
                mimetype='application/pdf'
            )
        elif html_path and os.path.isfile(html_path):
            return send_file(
                html_path,
                as_attachment=True,
                download_name=f'fraust_analysis_{analysis_id}.html',
                mimetype='text/html'
            )
        return jsonify({'error': 'PDF could not be generated'}), 500

    except Exception as e:
        logger.error(f"Error exporting analysis PDF: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/export/<int:analysis_id>')
def export_analysis(analysis_id):
    """Export analysis results as HTML report (PDF requires wkhtmltopdf)"""
    try:
        analysis = db.session.get(AnalysisResult, analysis_id)
        if not analysis:
            return jsonify({'error': 'Analysis not found'}), 404
        
        # Build a lightweight report from the analysis record
        try:
            results = json.loads(analysis.results) if analysis.results else []
            insights = json.loads(analysis.insights) if analysis.insights else []
        except Exception:
            results, insights = [], []

        report_data = report_generator.generate_report(
            file_id=analysis.report_id,
            query=analysis.query,
            results=results,
            insights=insights
        )
        html_path = report_data.get('html_path')
        pdf_path  = report_data.get('pdf_path')

        # Prefer PDF if it was successfully generated, otherwise serve HTML
        if pdf_path and os.path.isfile(pdf_path):
            return send_file(
                pdf_path,
                as_attachment=True,
                download_name=f'ufdr_analysis_{analysis_id}.pdf',
                mimetype='application/pdf'
            )
        elif html_path and os.path.isfile(html_path):
            return send_file(
                html_path,
                as_attachment=True,
                download_name=f'ufdr_analysis_{analysis_id}.html',
                mimetype='text/html'
            )
        else:
            return jsonify({'error': 'Report file could not be generated'}), 500
    
    except Exception as e:
        logger.error(f"Error exporting analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/ai/insights/<int:report_id>')
def get_ai_insights(report_id):
    """Get AI insights for a specific report"""
    try:
        insights = AIInsight.query.filter_by(report_id=report_id).order_by(AIInsight.timestamp.desc()).all()
        return jsonify([insight.to_dict() for insight in insights])
    except Exception as e:
        logger.error(f"Error getting AI insights: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/ai/patterns/<int:report_id>')
def get_forensic_patterns(report_id):
    """Get detected forensic patterns for a specific report"""
    try:
        patterns = ForensicPattern.query.filter_by(report_id=report_id).order_by(ForensicPattern.timestamp.desc()).all()
        return jsonify([pattern.to_dict() for pattern in patterns])
    except Exception as e:
        logger.error(f"Error getting forensic patterns: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/ai/risk-assessment/<int:report_id>')
def get_risk_assessment(report_id):
    """Get risk assessment for a specific report"""
    try:
        risk_assessment = RiskAssessment.query.filter_by(report_id=report_id).order_by(RiskAssessment.timestamp.desc()).first()
        if not risk_assessment:
            return jsonify({'error': 'Risk assessment not found'}), 404
        return jsonify(risk_assessment.to_dict())
    except Exception as e:
        logger.error(f"Error getting risk assessment: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/ai/model-info')
def get_model_info():
    """Get information about loaded AI models"""
    try:
        model_info = advanced_ai_processor.get_model_info()
        return jsonify(model_info)
    except Exception as e:
        logger.error(f"Error getting model info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/ai/comprehensive-analysis/<int:report_id>', methods=['POST'])
def comprehensive_analysis(report_id):
    """Perform comprehensive AI analysis on a report"""
    try:
        # Get report data
        report = db.session.get(UFDRReport, report_id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        # Gather all data
        chat_records = ChatRecord.query.filter_by(report_id=report_id).all()
        call_records = CallRecord.query.filter_by(report_id=report_id).all()
        image_records = ImageRecord.query.filter_by(report_id=report_id).all()
        
        query_data = {
            'chats': [chat.to_dict() for chat in chat_records],
            'calls': [call.to_dict() for call in call_records],
            'images': [image.to_dict() for image in image_records]
        }
        
        # Perform comprehensive analysis
        results = advanced_ai_processor.process_query("comprehensive analysis", file_id=report_id, data=query_data)
        
        # Save comprehensive analysis result
        analysis = AnalysisResult(
            report_id=report_id,
            query="comprehensive analysis",
            query_type="comprehensive",
            results=json.dumps(results.get('results', [])),
            ai_analysis=json.dumps(results.get('ai_analysis', {})),
            insights=json.dumps(results.get('insights', [])),
            confidence_score=results.get('confidence_score', 0.0),
            processing_method='advanced_ai',
            timestamp=datetime.utcnow()
        )
        db.session.add(analysis)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'analysis': results,
            'analysis_id': analysis.id
        })
    
    except Exception as e:
        logger.error(f"Error in comprehensive analysis: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/generate-report/<int:report_id>')
def generate_report(report_id):
    """Generate a comprehensive report for a specific case"""
    try:
        # Get report data
        report = db.session.get(UFDRReport, report_id)
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        # Get analysis results for this report - simplified approach
        try:
            analysis_results = AnalysisResult.query.filter_by(report_id=report_id).order_by(AnalysisResult.timestamp.desc()).all()
        except Exception as db_error:
            logger.warning(f"Database query failed, using empty results: {db_error}")
            analysis_results = []
        
        # Prepare data for report generation
        query = f"Comprehensive Analysis - Case: {report.case_number} - {report.case_title or 'Untitled Case'}"
        results = []
        insights = []
        
        for analysis in analysis_results:
            if analysis.results:
                try:
                    results.extend(json.loads(analysis.results))
                except:
                    results.append(analysis.results)
            if analysis.insights:
                try:
                    insights.extend(json.loads(analysis.insights))
                except:
                    insights.append(analysis.insights)
        
        # Generate the report (already inside app context as this is a route handler)
        report_data = report_generator.generate_report(
            file_id=report_id,
            query=query,
            results=results,
            insights=insights
        )
        
        return jsonify({
            'success': True,
            'report_id': report_data['report_id'],
            'html_path': report_data['html_path'],
            'pdf_path': report_data.get('pdf_path'),
            'message': 'Report generated successfully'
        })
    
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/view-report/<report_id>')
def view_report(report_id):
    """View a generated report"""
    try:
        report_info = report_generator.get_report_by_id(report_id)
        if not report_info or not report_info.get('html_path'):
            return jsonify({'error': 'Report not found'}), 404
        
        return send_file(report_info['html_path'])
    
    except Exception as e:
        logger.error(f"Error viewing report: {str(e)}")
        return jsonify({'error': str(e)}), 500

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'json', 'xml', 'csv', 'txt'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_ufdr_data(report_id, ufdr_data):
    """Process and store UFDR data in database"""
    try:
        # Process chat records
        if 'chats' in ufdr_data:
            for chat in ufdr_data['chats']:
                chat_record = ChatRecord(
                    report_id=report_id,
                    sender=chat.get('sender', ''),
                    receiver=chat.get('receiver', ''),
                    message=chat.get('message', ''),
                    timestamp=chat.get('timestamp'),
                    platform=chat.get('platform', '')
                )
                db.session.add(chat_record)
        
        # Process call records
        if 'calls' in ufdr_data:
            for call in ufdr_data['calls']:
                call_record = CallRecord(
                    report_id=report_id,
                    caller=call.get('caller', ''),
                    callee=call.get('callee', ''),
                    duration=call.get('duration', 0),
                    timestamp=call.get('timestamp'),
                    call_type=call.get('type', '')
                )
                db.session.add(call_record)
        
        # Process image records
        if 'images' in ufdr_data:
            for image in ufdr_data['images']:
                image_record = ImageRecord(
                    report_id=report_id,
                    filename=image.get('filename', ''),
                    filepath=image.get('filepath', ''),
                    image_metadata=json.dumps(image.get('metadata', {})),
                    timestamp=image.get('timestamp')
                )
                db.session.add(image_record)
        
        # Update report status
        report = db.session.get(UFDRReport, report_id)
        report.status = 'completed'
        db.session.commit()
        
        logger.info(f"Successfully processed UFDR data for report {report_id}")
    
    except Exception as e:
        logger.error(f"Error processing UFDR data: {str(e)}")
        # Update report status to failed
        report = db.session.get(UFDRReport, report_id)
        if report:
            report.status = 'failed'
            db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        print("🔧 Creating database tables...")
        db.create_all()
        print("✅ Database created successfully!")
        
        # Verify tables were created
        import sqlite3
        try:
            conn = sqlite3.connect('ufdr_analysis.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"📋 Created tables: {[table[0] for table in tables]}")
            
            # Check ufdr_reports columns
            cursor.execute("PRAGMA table_info(ufdr_reports)")
            columns = cursor.fetchall()
            print(f"📋 UFDR Reports columns: {[col[1] for col in columns]}")
            conn.close()
        except Exception as e:
            print(f"⚠️  Error verifying database: {e}")
    
    print("🚀 Starting application...")
    app.run(debug=True, host='0.0.0.0', port=5000)