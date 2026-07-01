from datetime import datetime
import json
from flask_sqlalchemy import SQLAlchemy

# Initialize db here to avoid circular imports
db = SQLAlchemy()

class UFDRReport(db.Model):
    """Model for UFDR report metadata"""
    __tablename__ = 'ufdr_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(100), nullable=False)
    case_title = db.Column(db.String(255))
    investigating_officer = db.Column(db.String(255))
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='processing')  # processing, completed, failed
    
    # Relationships
    chat_records = db.relationship('ChatRecord', backref='report', lazy=True, cascade='all, delete-orphan')
    call_records = db.relationship('CallRecord', backref='report', lazy=True, cascade='all, delete-orphan')
    image_records = db.relationship('ImageRecord', backref='report', lazy=True, cascade='all, delete-orphan')
    analysis_results = db.relationship('AnalysisResult', backref='report', lazy=True, cascade='all, delete-orphan')
    ai_insights = db.relationship('AIInsight', backref='report', lazy=True, cascade='all, delete-orphan')
    forensic_patterns = db.relationship('ForensicPattern', backref='report', lazy=True, cascade='all, delete-orphan')
    risk_assessments = db.relationship('RiskAssessment', backref='report', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self):
        return {
            'id': self.id,
            'case_number': self.case_number,
            'case_title': self.case_title,
            'investigating_officer': self.investigating_officer,
            'filename': self.filename,
            'upload_date': self.upload_date.isoformat(),
            'status': self.status
        }

class ChatRecord(db.Model):
    """Model for chat/message records"""
    __tablename__ = 'chat_records'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    sender = db.Column(db.String(255))
    receiver = db.Column(db.String(255))
    message = db.Column(db.Text)
    timestamp = db.Column(db.DateTime)
    platform = db.Column(db.String(100))  # WhatsApp, Telegram, SMS, etc.
    
    def to_dict(self):
        return {
            'id': self.id,
            'sender': self.sender,
            'receiver': self.receiver,
            'message': self.message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'platform': self.platform
        }

class CallRecord(db.Model):
    """Model for call records"""
    __tablename__ = 'call_records'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    caller = db.Column(db.String(255))
    callee = db.Column(db.String(255))
    duration = db.Column(db.Integer)  # Duration in seconds
    timestamp = db.Column(db.DateTime)
    call_type = db.Column(db.String(50))  # incoming, outgoing, missed
    
    def to_dict(self):
        return {
            'id': self.id,
            'caller': self.caller,
            'callee': self.callee,
            'duration': self.duration,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'call_type': self.call_type
        }

class ImageRecord(db.Model):
    """Model for image/media records"""
    __tablename__ = 'image_records'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    filename = db.Column(db.String(255))
    filepath = db.Column(db.String(500))
    image_metadata = db.Column(db.Text)  # JSON string of metadata
    timestamp = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'filepath': self.filepath,
            'metadata': json.loads(self.image_metadata) if self.image_metadata else {},
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

class AnalysisResult(db.Model):
    """Enhanced model for storing AI analysis results"""
    __tablename__ = 'analysis_results'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    query = db.Column(db.Text, nullable=False)
    query_type = db.Column(db.String(50))  # chat, call, image, crypto, foreign, general
    results = db.Column(db.Text)  # JSON string of results
    ai_analysis = db.Column(db.Text)  # JSON string of AI analysis
    insights = db.Column(db.Text)  # JSON string of insights
    confidence_score = db.Column(db.Float, default=0.0)
    processing_method = db.Column(db.String(50))  # traditional, ai_enhanced, advanced_ai
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'query': self.query,
            'query_type': self.query_type,
            'results': json.loads(self.results) if self.results else {},
            'ai_analysis': json.loads(self.ai_analysis) if self.ai_analysis else {},
            'insights': json.loads(self.insights) if self.insights else [],
            'confidence_score': self.confidence_score,
            'processing_method': self.processing_method,
            'timestamp': self.timestamp.isoformat()
        }

class AIInsight(db.Model):
    """Model for storing AI-generated insights"""
    __tablename__ = 'ai_insights'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    analysis_id = db.Column(db.Integer, db.ForeignKey('analysis_results.id'), nullable=True)
    insight_type = db.Column(db.String(50))  # pattern, anomaly, risk, recommendation
    insight_text = db.Column(db.Text, nullable=False)
    confidence_score = db.Column(db.Float, default=0.0)
    severity_level = db.Column(db.String(20))  # low, medium, high, critical
    metadata_json = db.Column("metadata", db.Text)  # ✅ fixed
    extra_metadata = db.Column(db.String(255))      # ✅ renamed from meta_data
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'report_id': self.report_id,
            'analysis_id': self.analysis_id,
            'insight_type': self.insight_type,
            'insight_text': self.insight_text,
            'confidence_score': self.confidence_score,
            'severity_level': self.severity_level,
            'metadata': json.loads(self.metadata_json) if self.metadata_json else {},
            'timestamp': self.timestamp.isoformat()
        }

class ForensicPattern(db.Model):
    """Model for storing detected forensic patterns"""
    __tablename__ = 'forensic_patterns'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    pattern_type = db.Column(db.String(50))  # crypto_address, phone_number, suspicious_keyword, etc.
    pattern_category = db.Column(db.String(50))  # bitcoin, ethereum, drugs, weapons, etc.
    pattern_value = db.Column(db.Text, nullable=False)  # The actual pattern found
    context = db.Column(db.Text)  # Context where pattern was found
    confidence_score = db.Column(db.Float, default=0.0)
    risk_level = db.Column(db.String(20))  # low, medium, high, critical
    metadata_json = db.Column("metadata", db.Text)  # ✅ fixed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'report_id': self.report_id,
            'pattern_type': self.pattern_type,
            'pattern_category': self.pattern_category,
            'pattern_value': self.pattern_value,
            'context': self.context,
            'confidence_score': self.confidence_score,
            'risk_level': self.risk_level,
            'metadata': json.loads(self.metadata_json) if self.metadata_json else {},
            'timestamp': self.timestamp.isoformat()
        }

class RiskAssessment(db.Model):
    """Model for storing risk assessments"""
    __tablename__ = 'risk_assessments'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('ufdr_reports.id'), nullable=False)
    overall_risk_level = db.Column(db.String(20))  # low, medium, high, critical
    risk_score = db.Column(db.Float, default=0.0)
    risk_factors = db.Column(db.Text)  # JSON string of risk factors
    recommendations = db.Column(db.Text)  # JSON string of recommendations
    assessment_method = db.Column(db.String(50))  # ai_enhanced, traditional, hybrid
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'report_id': self.report_id,
            'overall_risk_level': self.overall_risk_level,
            'risk_score': self.risk_score,
            'risk_factors': json.loads(self.risk_factors) if self.risk_factors else {},
            'recommendations': json.loads(self.recommendations) if self.recommendations else [],
            'assessment_method': self.assessment_method,
            'timestamp': self.timestamp.isoformat()
        }

class ModelPerformance(db.Model):
    """Model for tracking AI model performance"""
    __tablename__ = 'model_performance'
    
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(100), nullable=False)
    model_version = db.Column(db.String(50))
    query_type = db.Column(db.String(50))
    processing_time = db.Column(db.Float)  # Processing time in seconds
    accuracy_score = db.Column(db.Float)
    confidence_score = db.Column(db.Float)
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text)
    metadata_json = db.Column("metadata", db.Text)  # ✅ fixed
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'model_name': self.model_name,
            'model_version': self.model_version,
            'query_type': self.query_type,
            'processing_time': self.processing_time,
            'accuracy_score': self.accuracy_score,
            'confidence_score': self.confidence_score,
            'success': self.success,
            'error_message': self.error_message,
            'metadata': json.loads(self.metadata_json) if self.metadata_json else {},
            'timestamp': self.timestamp.isoformat()
        }