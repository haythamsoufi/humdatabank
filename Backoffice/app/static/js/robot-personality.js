// Robot Personality System for Chatbot FAB

document.addEventListener('DOMContentLoaded', function() {
    const aiChatbotFAB = document.getElementById('aiChatbotFAB');

    // --- Robot Personality System ---
    const RobotPersonality = {
        expressions: [
            { name: 'blinking', duration: 300, weight: 25 },
            { name: 'yawning', duration: 2000, weight: 8 },
            { name: 'tired', duration: 3000, weight: 6 },
            { name: 'excited', duration: 1000, weight: 12 },
            { name: 'thinking', duration: 2000, weight: 15 },
            { name: 'happy', duration: 1500, weight: 18 }
        ],

        currentExpression: null,
        isActive: true,
        nextExpressionTimeout: null,

        init() {
            if (!aiChatbotFAB) return;
            this.scheduleNextExpression();

            // Add hover effects
            aiChatbotFAB.addEventListener('mouseenter', () => {
                if (!this.currentExpression) {
                    this.triggerExpression('excited');
                }
            });

            // Pause personality when chat is open
            const chatWidget = document.getElementById('aiChatWidget');
            if (chatWidget) {
                const observer = new MutationObserver((mutations) => {
                    mutations.forEach((mutation) => {
                        if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                            if (chatWidget.classList.contains('chat-open')) {
                                this.pausePersonality();
                                this.triggerExpression('thinking', true); // Keep thinking while chat is open
                            } else {
                                this.resumePersonality();
                            }
                        }
                    });
                });
                observer.observe(chatWidget, { attributes: true, attributeFilter: ['class'] });
            }
        },

        triggerExpression(expressionName, persistent = false) {
            if (!aiChatbotFAB || !this.isActive) return;

            // Clear any existing expression
            this.clearCurrentExpression();

            // Add new expression
            aiChatbotFAB.classList.add(`robot-${expressionName}`);
            this.currentExpression = expressionName;

            if (!persistent) {
                const expression = this.expressions.find(exp => exp.name === expressionName);
                const duration = expression ? expression.duration : 1000;

                setTimeout(() => {
                    this.clearCurrentExpression();
                    if (this.isActive) {
                        this.scheduleNextExpression();
                    }
                }, duration);
            }
        },

        clearCurrentExpression() {
            if (!aiChatbotFAB) return;

            this.expressions.forEach(exp => {
                aiChatbotFAB.classList.remove(`robot-${exp.name}`);
            });
            this.currentExpression = null;
        },

        getRandomExpression() {
            // Weighted random selection
            const totalWeight = this.expressions.reduce((sum, exp) => sum + exp.weight, 0);
            let random = Math.random() * totalWeight;

            for (let exp of this.expressions) {
                random -= exp.weight;
                if (random <= 0) {
                    return exp.name;
                }
            }
            return this.expressions[0].name; // Fallback
        },

        scheduleNextExpression() {
            if (!this.isActive) return;

            // Random delay between 3-8 seconds for natural feeling
            const delay = Math.random() * 5000 + 3000;

            this.nextExpressionTimeout = setTimeout(() => {
                if (this.isActive && !this.currentExpression) {
                    const expression = this.getRandomExpression();
                    this.triggerExpression(expression);
                }
            }, delay);
        },

        pausePersonality() {
            this.isActive = false;
            if (this.nextExpressionTimeout) {
                clearTimeout(this.nextExpressionTimeout);
                this.nextExpressionTimeout = null;
            }
        },

        resumePersonality() {
            this.isActive = true;
            this.clearCurrentExpression();
            this.scheduleNextExpression();
        }
    };

    // Make RobotPersonality globally available
    window.RobotPersonality = RobotPersonality;

    // Initialize robot personality if FAB exists
    if (aiChatbotFAB) {
        // Small delay to ensure everything is loaded
        setTimeout(() => {
            RobotPersonality.init();
        }, 1000);

        // Pause personality when user is inactive for too long
        let userInactivityTimer;
        const resetInactivityTimer = () => {
            clearTimeout(userInactivityTimer);
            if (!RobotPersonality.isActive) {
                RobotPersonality.resumePersonality();
            }

            // Set robot to tired state after 2 minutes of inactivity
            userInactivityTimer = setTimeout(() => {
                if (RobotPersonality.isActive) {
                    RobotPersonality.triggerExpression('tired');
                    // Reduce activity when user is inactive
                    setTimeout(() => {
                        if (RobotPersonality.isActive) {
                            RobotPersonality.pausePersonality();
                        }
                    }, 3000);
                }
            }, 120000); // 2 minutes
        };

        // Track user activity
        ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'].forEach(event => {
            document.addEventListener(event, resetInactivityTimer, { passive: true });
        });

        resetInactivityTimer();
    }
});
