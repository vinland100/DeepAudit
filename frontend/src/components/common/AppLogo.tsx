import React from 'react';

/**
 * AppLogo Component
 * A professional SVG-based logo representing an AI Code Review Bot.
 * Supports theme switching and various sizes.
 */

interface AppLogoProps {
    className?: string;
    size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
    showText?: boolean;
    collapsed?: boolean;
    theme?: 'dark' | 'light'; // Optional override
    subtitle?: string;
}

const AppLogo: React.FC<AppLogoProps> = ({
    className = "",
    size = 'md',
    showText = true,
    collapsed = false,
    subtitle = "AI Code Review Bot"
}) => {
    // Size mapping for both icon and text
    const sizeMap = {
        sm: { icon: 'w-6 h-6', text: 'text-lg', sub: 'text-[8px]', gap: 'gap-2' },
        md: { icon: 'w-10 h-10', text: 'text-xl', sub: 'text-[10px]', gap: 'gap-3' },
        lg: { icon: 'w-14 h-14', text: 'text-3xl', sub: 'text-sm', gap: 'gap-4' },
        xl: { icon: 'w-20 h-20', text: 'text-4xl', sub: 'text-base', gap: 'gap-5' },
        '2xl': { icon: 'w-24 h-24', text: 'text-5xl', sub: 'text-lg', gap: 'gap-6' }
    };

    const currentSize = sizeMap[size];

    return (
        <div className={`flex items-center ${currentSize.gap} transition-all duration-300 ${className} ${collapsed ? 'justify-center' : ''}`}>
            {/* Logo Icon Container */}
            <div className={`relative flex-shrink-0 ${currentSize.icon} transition-transform duration-300 hover:scale-110 group`}>
                {/* SVG Logo */}
                <svg
                    viewBox="0 0 100 100"
                    fill="none"
                    xmlns="http://www.w3.org/2000/svg"
                    className="w-full h-full drop-shadow-[0_0_15px_rgba(255,107,44,0.3)]"
                >
                    <defs>
                        <linearGradient id="logo-grad-primary" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" stopColor="hsl(var(--primary))" />
                            <stop offset="100%" stopColor="hsl(var(--primary) / 0.7)" />
                        </linearGradient>
                        <filter id="logo-glow" x="-20%" y="-20%" width="140%" height="140%">
                            <feGaussianBlur stdDeviation="3" result="blur" />
                            <feComposite in="SourceGraphic" in2="blur" operator="over" />
                        </filter>
                    </defs>

                    {/* Outer Hexagon Frame */}
                    <path
                        d="M50 5 L90 28 L90 72 L50 95 L10 72 L10 28 Z"
                        stroke="url(#logo-grad-primary)"
                        strokeWidth="4"
                        fill="currentColor"
                        className="text-primary/10 transition-colors duration-300"
                    />

                    {/* Circuit Like Lines */}
                    <path
                        d="M30 15 L50 5 L70 15"
                        stroke="url(#logo-grad-primary)"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeOpacity="0.5"
                    />
                    <path
                        d="M30 85 L50 95 L70 85"
                        stroke="url(#logo-grad-primary)"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeOpacity="0.5"
                    />

                    {/* Brackets < > */}
                    <path
                        d="M32 35 L18 50 L32 65"
                        stroke="url(#logo-grad-primary)"
                        strokeWidth="7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        filter="url(#logo-glow)"
                        className="group-hover:translate-x-[-2px] transition-transform duration-300"
                    />
                    <path
                        d="M68 35 L82 50 L68 65"
                        stroke="url(#logo-grad-primary)"
                        strokeWidth="7"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        filter="url(#logo-glow)"
                        className="group-hover:translate-x-[2px] transition-transform duration-300"
                    />

                    {/* Central AI Eye Entity */}
                    <circle
                        cx="50"
                        cy="50"
                        r="20"
                        stroke="url(#logo-grad-primary)"
                        strokeWidth="2"
                        fill="var(--cyber-bg-elevated)"
                        className="transition-colors duration-300"
                    />

                    {/* Glowing Core */}
                    <circle
                        cx="50"
                        cy="50"
                        r="12"
                        fill="url(#logo-grad-primary)"
                        className="animate-pulse"
                        filter="url(#logo-glow)"
                    />

                    {/* Lens Highlight */}
                    <circle
                        cx="46"
                        cy="46"
                        r="4"
                        fill="white"
                        fillOpacity="0.8"
                    />

                    {/* Scanline Effect across the icon */}
                    <rect
                        x="15"
                        y="48"
                        width="70"
                        height="4"
                        fill="url(#logo-grad-primary)"
                        fillOpacity="0.2"
                        className="animate-[scan_3s_ease-in-out_infinite]"
                    >
                        <animate
                            attributeName="y"
                            values="25;75;25"
                            dur="3s"
                            repeatCount="indefinite"
                        />
                    </rect>
                </svg>

                {/* Outer Glow for Hover */}
                <div className="absolute inset-0 bg-primary/20 rounded-xl blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
            </div>

            {/* Text Section */}
            {showText && !collapsed && (
                <div className="flex flex-col transition-all duration-300">
                    <div
                        className={`${currentSize.text} font-bold tracking-wider font-mono leading-tight`}
                        style={{
                            textShadow: '0 0 25px rgba(255,107,44,0.4)',
                            color: 'var(--cyber-text)'
                        }}
                    >
                        <span className="text-primary">DEEP</span>
                        <span>AUDIT</span>
                    </div>
                    <div className={`${currentSize.sub} text-muted-foreground font-mono tracking-[0.2em] uppercase mt-0.5 whitespace-nowrap`}>
                        {subtitle}
                    </div>
                </div>
            )}
        </div>
    );
};

export default AppLogo;
