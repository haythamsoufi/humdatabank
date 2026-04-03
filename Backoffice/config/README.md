# Configuration Files

This directory contains all configuration files, templates, and setup scripts for the NGO Databank Backoffice system.

## 📋 Available Files

### Core Configuration
- **config.py** - Main application configuration file
- **email_config_template.txt** - Email service configuration template
- **libretranslate_config.txt** - LibreTranslate service configuration

### Setup Scripts
- **setup_email.py** - Email service setup and configuration script
- **setup_libretranslate.ps1** - LibreTranslate setup script for Windows
- **update_email_config.ps1** - Email configuration update script for Windows
- **gmail_filter_instructions.txt** - Instructions for setting up Gmail filters

## 🔧 Configuration Guidelines

### Environment Variables
- Use `.env` file in the root directory for sensitive configuration
- Never commit sensitive data to version control
- Use environment-specific configuration files when needed

### Email Configuration
1. Copy `email_config_template.txt` to create your email configuration
2. Update the configuration with your email service details
3. Run `setup_email.py` to apply the configuration
4. Follow `gmail_filter_instructions.txt` for Gmail-specific setup

### LibreTranslate Setup
1. Use `libretranslate_config.txt` as a reference for configuration
2. Run `setup_libretranslate.ps1` on Windows systems
3. Ensure proper network access for translation services

## 🔒 Security Considerations

- Keep sensitive configuration data in environment variables
- Use secure file permissions for configuration files
- Regularly update configuration templates
- Document all configuration changes

## 📝 Configuration Workflow

1. **Development**: Use local configuration files
2. **Testing**: Use test environment configuration
3. **Production**: Use environment variables and secure configuration
4. **Backup**: Maintain backup copies of critical configurations 
