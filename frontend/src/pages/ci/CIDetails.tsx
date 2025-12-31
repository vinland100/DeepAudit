import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bot, GitPullRequest, MessageSquare, ChevronLeft, Calendar, FileText } from "lucide-react";
import { marked } from 'marked';
import { format } from 'date-fns';

interface PRReview {
    id: string;
    pr_number: number;
    event_type: string;
    summary: string;
    full_report: string;
    context_used: string;
    created_at: string;
}

const CIDetails: React.FC = () => {
    const { id } = useParams<{ id: string }>();
    const [reviews, setReviews] = useState<PRReview[]>([]);
    const [loading, setLoading] = useState(true);
    const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

    useEffect(() => {
        const fetchReviews = async () => {
            try {
                const res = await fetch(`/api/v1/ci/projects/${id}/reviews`);
                if (res.ok) {
                    const data = await res.json();
                    setReviews(data);
                }
            } catch (error) {
                console.error(error);
            } finally {
                setLoading(false);
            }
        };
        fetchReviews();
    }, [id]);

    const toggleExpand = (reviewId: string) => {
        const newSet = new Set(expandedIds);
        if (newSet.has(reviewId)) {
            newSet.delete(reviewId);
        } else {
            newSet.add(reviewId);
        }
        setExpandedIds(newSet);
    };

    const getEventIcon = (type: string) => {
        switch (type) {
            case 'opened': return <GitPullRequest className="w-5 h-5 text-blue-500" />;
            case 'synchronize': return <GitPullRequest className="w-5 h-5 text-yellow-500" />;
            case 'comment': return <MessageSquare className="w-5 h-5 text-green-500" />;
            default: return <Bot className="w-5 h-5" />;
        }
    };

    const renderMarkdown = (content: string) => {
        return { __html: marked.parse(content) as string };
    };

    if (loading) return <div className="p-8 text-center text-muted-foreground">Loading timeline...</div>;

    return (
        <div className="p-6 space-y-6 max-w-5xl mx-auto">
            <div className="flex items-center gap-4 mb-6">
                <Link to="/ci-integration">
                    <Button variant="ghost" size="icon">
                        <ChevronLeft className="w-5 h-5" />
                    </Button>
                </Link>
                <div>
                    <h1 className="text-2xl font-bold">Review History</h1>
                    <p className="text-muted-foreground text-sm">Project ID: {id}</p>
                </div>
            </div>

            <div className="space-y-6 relative border-l-2 border-muted ml-4 pl-8 pb-8">
                {reviews.map((review) => (
                    <div key={review.id} className="relative">
                        {/* Dot indicator */}
                        <div className="absolute -left-[41px] top-4 w-5 h-5 rounded-full bg-background border-2 border-primary ring-4 ring-background flex items-center justify-center">
                            <div className="w-2 h-2 rounded-full bg-primary" />
                        </div>

                        <Card className={`transition-all duration-300 ${expandedIds.has(review.id) ? 'ring-2 ring-primary/20' : ''}`}>
                            <CardHeader className="pb-2">
                                <div className="flex justify-between items-start">
                                    <div className="flex items-center gap-2">
                                        <Badge variant="secondary" className="gap-1 px-2 py-1">
                                            {getEventIcon(review.event_type)}
                                            <span className="capitalize">{review.event_type}</span>
                                        </Badge>
                                        <span className="font-mono text-sm text-muted-foreground">
                                            #{review.pr_number}
                                        </span>
                                    </div>
                                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                        <Calendar className="w-3 h-3" />
                                        {format(new Date(review.created_at), 'yyyy-MM-dd HH:mm:ss')}
                                    </div>
                                </div>
                                <CardTitle className="text-lg mt-2 font-medium">
                                    <div
                                        className="prose prose-invert prose-sm max-w-none line-clamp-2"
                                        dangerouslySetInnerHTML={renderMarkdown(review.summary.split('\n')[0])}
                                    />
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className={`relative ${expandedIds.has(review.id) ? '' : 'max-h-24 overflow-hidden mask-gradient-b'}`}>
                                    <div className="bg-muted/30 p-4 rounded-md text-sm font-mono overflow-auto">
                                        <div
                                            className="prose prose-invert max-w-none"
                                            dangerouslySetInnerHTML={renderMarkdown(review.full_report)}
                                        />
                                    </div>

                                    {/* Context Debug Info */}
                                    {expandedIds.has(review.id) && review.context_used && review.context_used !== "[]" && (
                                        <div className="mt-4 pt-4 border-t border-border">
                                            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground mb-2">
                                                <FileText className="w-3 h-3" />
                                                RAG Context Used:
                                            </div>
                                            <div className="flex flex-wrap gap-2">
                                                {JSON.parse(review.context_used).map((file: string, idx: number) => (
                                                    <Badge key={idx} variant="outline" className="text-xs font-normal">
                                                        {file}
                                                    </Badge>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>

                                <Button
                                    variant="ghost"
                                    size="sm"
                                    className="w-full mt-2 text-primary hover:text-primary/80"
                                    onClick={() => toggleExpand(review.id)}
                                >
                                    {expandedIds.has(review.id) ? "Collapse" : "Read Full Report"}
                                </Button>
                            </CardContent>
                        </Card>
                    </div>
                ))}

                {reviews.length === 0 && (
                    <div className="text-center py-12 text-muted-foreground">
                        No reviews found for this project yet.
                    </div>
                )}
            </div>
        </div>
    );
};

export default CIDetails;
