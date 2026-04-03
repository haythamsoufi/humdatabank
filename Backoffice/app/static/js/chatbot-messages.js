/**
 * IFRC Chatbot Static Messages and Knowledge Base
 * Centralized location for all chatbot text content
 */

const ChatbotMessages = {
    // Greeting messages by language (short; used only when user says hi in fallback mode)
    greetings: {
        en: "Hello! How can I help you?",
        es: "¡Hola! ¿En qué puedo ayudarte?",
        fr: "Bonjour! Comment puis-je vous aider?",
        ar: "مرحباً! كيف يمكنني مساعدتك؟",
        hi: "नमस्ते! मैं आपकी कैसे मदद कर सकता हूं?"
    },

    // Error messages by language
    errors: {
        connectionError: {
            en: "I'm sorry, but I'm having trouble connecting right now. Please check your internet connection and try again.",
            es: "Lo siento, pero tengo problemas para conectarme ahora. Por favor verifica tu conexión a internet e intenta de nuevo.",
            fr: "Je suis désolé, mais j'ai des problèmes de connexion maintenant. Veuillez vérifier votre connexion internet et réessayer.",
            ar: "أعتذر، لكن لدي مشاكل في الاتصال الآن. يرجى التحقق من اتصالك بالإنترنت والمحاولة مرة أخرى.",
            hi: "मुझे खेद है, लेकिन मुझे अभी कनेक्ट होने में समस्या हो रही है। कृपया अपना इंटरनेट कनेक्शन जांचें और फिर से प्रयास करें।"
        },
        apiUnavailable: {
            en: "⚠️ AI service is temporarily unavailable. Using local knowledge base to help you.",
            es: "⚠️ El servicio de IA no está disponible temporalmente. Usando la base de conocimientos local para ayudarte.",
            fr: "⚠️ Le service IA est temporairement indisponible. Utilisation de la base de connaissances locale pour vous aider.",
            ar: "⚠️ خدمة الذكاء الاصطناعي غير متوفرة مؤقتاً. استخدام قاعدة المعرفة المحلية لمساعدتك.",
            hi: "⚠️ एआई सेवा अस्थायी रूप से अनुपलब्ध है। आपकी मदद के लिए स्थानीय ज्ञान आधार का उपयोग कर रहे हैं।"
        }
    },

    // UI strings (progress, tours, delete confirmation, message actions)
    // NOTE: When running inside the immersive chat page, server-side translations
    // are injected via window.CHAT_UI_STRINGS (Flask-Babel) and take precedence.
    // These English entries serve as the ultimate fallback.
    ui: {
        en: {
            newChat: 'New chat',
            loading: 'Loading…',
            noConversationsMatch: 'No conversations match your search.',
            deleteChat: 'Delete chat',
            deleteConversationConfirm: 'Delete this conversation? This cannot be undone.',
            deleteConversationTitle: 'Delete conversation?',
            clearAllConversationsConfirm: 'Delete all conversations? This cannot be undone.',
            clearAllConversationsTitle: 'Clear all conversations?',
            clearAll: 'Clear all',
            clearConversationConfirm: 'Are you sure you want to clear the entire conversation? This action cannot be undone.',
            clearConversationTitle: 'Clear Conversation?',
            clear: 'Clear',
            delete: 'Delete',
            cancel: 'Cancel',
            send: 'Send',
            stop: 'Stop',
            copy: 'Copy',
            copied: 'Copied!',
            like: 'Like',
            dislike: 'Dislike',
            feedbackReceived: 'Thanks, feedback received.',
            feedbackUnavailable: "Feedback isn't available for this message.",
            feedbackSendFailed: "Couldn't send feedback.",
            retry: 'Retry',
            edit: 'Edit',
            editMessage: 'Edit message',
            cancelEdit: 'Cancel edit',
            assistantIsTyping: 'Assistant is typing',
            preparingQuery: 'Preparing query…',
            stepsInProgress: 'Steps in progress',
            endTour: 'End Tour',
            serverError: 'Server error',
            requestCancelled: 'Request cancelled',
            aiPolicyAckRequired: 'Please acknowledge the AI policy to continue.',
            iUnderstand: 'I understand'
        }
    },

    // Local knowledge base for fallback responses
    knowledgeBase: {
        dashboard: {
            keywords: ['dashboard', 'home', 'main page', 'overview'],
            response: 'Your dashboard is your main control center! 🏠<br><br><strong>For Admins:</strong> Access comprehensive statistics, recent activities, user management shortcuts, and system overview.<br><br><strong>For Focal Points:</strong> View assigned forms, submission deadlines, and quick access to your tasks.<br><br>You can always return to the dashboard using the "Dashboard" link in the navigation or sidebar.'
        },

        template: {
            keywords: ['template', 'form template', 'create form', 'form builder'],
            response: 'Templates are the foundation of your data collection! 📋<br><br><strong>Location:</strong> Form & Data Management → Manage Templates<br><br><strong>What you can do:</strong><br>• Create new templates with custom fields<br>• Add sections and organize your form structure<br>• Set up validation rules and conditional logic<br>• Use dynamic indicators from the Indicator Bank<br>• Configure repeating sections for complex data<br><br>Templates become the basis for assignments that users fill out.'
        },

        assignment: {
            keywords: ['assignment', 'assign', 'task', 'assign form'],
            response: 'Assignments connect your templates to specific users or countries! 🎯<br><br><strong>How it works:</strong><br>1. Choose a template<br>2. Select who should fill it out (users/countries)<br>3. Set deadlines and priorities<br>4. Track completion status<br><br><strong>Location:</strong> Form & Data Management → Manage Assignments<br><br>Users will see their assignments on their dashboard and can submit data through them.'
        },

        help: {
            keywords: ['help', 'how', 'what', 'guide'],
            get response() {
                const orgName = window.ORG_NAME || 'NGO Databank';
                return `I'm here to help you navigate the ${orgName}! 🤖<br><br><strong>Popular topics:</strong><br>• "How do I create a template?" - Form building<br>• "Where is the dashboard?" - Navigation<br>• "What are assignments?" - Task management<br>• "How do I submit data?" - Data collection<br>• "Where are the analytics?" - Reports and insights<br><br>Just ask me anything specific about the platform!`;
            }
        }
    },

    // Page type explanations for local fallback
    pageExplanations: {
        admin_dashboard: {
            title: 'Admin Dashboard',
            emoji: '🎯',
            description: `Your central hub for managing the entire platform. From here you can:<br>
                • View system statistics and recent activity<br>
                • Access all management tools via the sidebar<br>
                • Monitor platform health and user activity<br><br>
                <strong>🔧 Quick Actions:</strong> Use the sidebar to navigate to user management, templates, assignments, and more!`
        },

        user_dashboard: {
            title: 'Dashboard',
            emoji: '🎯',
            description: `Your personal workspace showing:<br>
                • Your assigned forms and deadlines<br>
                • Recent submissions and progress<br>
                • Important announcements<br><br>
                <strong>✅ Next Steps:</strong> Click on any pending assignment to start working on it!`
        },

        template_management: {
            title: 'Template Management',
            emoji: '🎯',
            description: `Create and edit form templates here:<br>
                • Build custom forms with drag-and-drop<br>
                • Add validation rules and conditional logic<br>
                • Use indicators from the Indicator Bank<br><br>
                <strong>💡 Tip:</strong> Templates are the foundation for all data collection!`
        },

        assignment_management: {
            title: 'Assignment Management',
            emoji: '🎯',
            description: `Assign templates to users or countries:<br>
                • Select templates and target recipients<br>
                • Set deadlines and priorities<br>
                • Track completion status<br><br>
                <strong>📋 Workflow:</strong> Template → Assignment → Data Collection`
        },

        user_management: {
            title: 'User Management Center',
            emoji: '🎯',
            description: `Comprehensive user administration for platform access control:<br>
                • <strong>Create Users:</strong> Add new Admin or Focal Point accounts<br>
                • <strong>Edit Profiles:</strong> Update names, emails, titles, and roles<br>
                • <strong>Role Assignment:</strong> Set Admin or Focal Point permissions<br>
                • <strong>Country Linking:</strong> Assign Focal Points to specific countries<br>
                • <strong>Access Control:</strong> Enable/disable accounts and manage permissions<br><br>
                <strong>👥 Role Details:</strong><br>
                • <strong>Admins:</strong> Full platform management and oversight<br>
                • <strong>Focal Points:</strong> Country-specific data collection and submission<br><br>
                <strong>💡 Tip:</strong> Use the table to view all users and their current assignments!`
        },

        country_management: {
            title: 'Country Management',
            emoji: '🎯',
            description: `Manage country data and assignments:<br>
                • Add and edit country information<br>
                • Assign focal points to countries<br>
                • Track regional groupings<br><br>
                <strong>🌍 Global Reach:</strong> Organize data collection by geographic regions`
        },

        indicator_bank: {
            title: 'Indicator Bank',
            emoji: '🎯',
            description: `Central repository for data indicators:<br>
                • Browse and search existing indicators<br>
                • Create new standardized indicators<br>
                • Organize by sector and subsector<br><br>
                <strong>📊 Standardization:</strong> Ensures consistent data collection across all forms`
        },

        analytics: {
            title: 'Analytics Dashboard',
            emoji: '🎯',
            description: `View platform insights and reports:<br>
                • User activity and engagement<br>
                • Submission trends and patterns<br>
                • System performance metrics<br><br>
                <strong>📈 Data-Driven:</strong> Make informed decisions based on platform usage data`
        },

        data_entry_form: {
            title: 'Data Entry Form',
            emoji: '🎯',
            description: `Submit your data here:<br>
                • Fill out all required fields (marked with *)<br>
                • Save drafts to continue later<br>
                • Upload supporting documents<br><br>
                <strong>💾 Remember:</strong> Save frequently and review before final submission!`
        },

        document_management: {
            title: 'Document Management',
            emoji: '🎯',
            description: `Organize and share files:<br>
                • Upload documents and organize in folders<br>
                • Set access permissions<br>
                • Share with specific users or groups<br><br>
                <strong>📁 File Organization:</strong> Keep your documents organized for easy access`
        },

        unknown: {
            title: 'Platform Page',
            emoji: '🎯',
            get description() {
                const orgName = window.ORG_NAME || 'NGO Databank';
                return `You're currently viewing a page within the ${orgName} platform.<br><br>
                <strong>💡 General Help:</strong><br>
                • Use the navigation menu to move between sections<br>
                • Look for action buttons to perform tasks<br>
                • Check for any forms or data tables on this page<br><br>
                <strong>❓ Need more help?</strong> Ask me about specific features you see on this page!`;
            }
        }
    },

    // Thank you responses
    thankYouResponses: {
        get en() {
            const orgName = window.ORG_NAME || 'NGO Databank';
            return `You're very welcome! 😊 I'm always here to help you make the most of the ${orgName}. Don't hesitate to ask if you need anything else!`;
        },
        es: '¡De nada! 😊 Siempre estoy aquí para ayudarte a aprovechar al máximo el Banco de Datos de IFRC. ¡No dudes en preguntar si necesitas algo más!',
        fr: 'De rien! 😊 Je suis toujours là pour vous aider à tirer le meilleur parti de la Banque de Données IFRC. N\'hésitez pas à demander si vous avez besoin d\'autre chose!',
        ar: 'على الرحب والسعة! 😊 أنا دائماً هنا لمساعدتك في الاستفادة القصوى من بنك بيانات الاتحاد الدولي. لا تتردد في السؤال إذا كنت بحاجة إلى أي شيء آخر!',
        hi: 'आपका स्वागत है! 😊 मैं हमेशा IFRC नेटवर्क डेटाबैंक का अधिकतम लाभ उठाने में आपकी मदद करने के लिए यहां हूं। यदि आपको कुछ और चाहिए तो पूछने में संकोच न करें!'
    },

    // Shown when AI is unavailable and user message did not match local fallback (e.g. knowledge base)
    defaultResponse: {
        en: "AI is not available. Please try again later.",
        es: "La IA no está disponible. Por favor, inténtelo de nuevo más tarde.",
        fr: "L'IA n'est pas disponible. Veuillez réessayer plus tard.",
        ar: "الذكاء الاصطناعي غير متوفر. يرجى المحاولة لاحقاً.",
        hi: "AI उपलब्ध नहीं है। कृपया बाद में पुनः प्रयास करें।"
    },

    // Page explanation request patterns
    pageExplanationPatterns: [
        'explain this page',
        'what is this page',
        'current page',
        'where am i',
        'what does this page do',
        'describe this page'
    ],

    // Thank you patterns
    thankYouPatterns: ['thank', 'thanks', 'thank you', 'appreciate'],

    // Greeting patterns
    greetingPatterns: ['hello', 'hi', 'hey', 'hola', 'bonjour'],

    // Debug mode messages
    debug: {
        apiCallStart: '🔵 API Call Starting',
        apiCallSuccess: '✅ API Call Successful',
        apiCallFailed: '⚠️ API Call Failed - Using Fallback',
        contextCollection: '📦 Collecting Page Context',
        payloadSize: 'Payload Size',
        responseSize: 'Response Size',
        apiAvailable: '🟢 Backoffice API Available',
        apiUnavailable: '🔴 Backoffice API Unavailable',
        usingFallback: '🟡 Using Local Knowledge Base'
    }
};

// Export for use in chatbot.js
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChatbotMessages;
}
// Also make it globally available
if (typeof window !== 'undefined') {
    window.ChatbotMessages = ChatbotMessages;
}
