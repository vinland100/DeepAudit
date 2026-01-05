import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { GitGraph, ArrowRight, Trash2, Clock } from "lucide-react";
import { formatDistanceToNowStrict } from 'date-fns';
import { zhCN } from 'date-fns/locale';

interface CIProject {
    id: string;
    name: string;
    description: string;
    repository_url: string;
    latest_pr_activity: string;
    created_at: string;
}

const CIProjects: React.FC = () => {
    const [projects, setProjects] = useState<CIProject[]>([]);
    const [loading, setLoading] = useState(true);

    const fetchProjects = async () => {
        try {
            const res = await fetch('/api/v1/ci/projects');
            if (res.ok) {
                const data = await res.json();
                setProjects(data);
            }
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchProjects();
    }, []);

    const handleDelete = async (id: string) => {
        if (!confirm("Are you sure? This will delete all review history.")) return;
        try {
            const res = await fetch(`/api/v1/ci/projects/${id}`, { method: 'DELETE' });
            if (res.ok) {
                fetchProjects();
            }
        } catch (error) {
            console.error(error);
        }
    };

    if (loading) return <div className="p-8 text-center text-muted-foreground">Loading projects...</div>;

    return (
        <div className="p-6 space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold flex items-center gap-3">
                        <GitGraph className="w-8 h-8 text-primary" />
                        CI Integration
                    </h1>
                    <p className="text-muted-foreground mt-2">
                        Automatically discovered projects from Gitea Webhooks.
                    </p>
                </div>
            </div>

            {projects.length === 0 ? (
                <Card className="bg-muted/30 border-dashed">
                    <CardContent className="flex flex-col items-center justify-center p-12 text-center">
                        <GitGraph className="w-12 h-12 text-muted-foreground mb-4 opacity-50" />
                        <h3 className="text-xl font-semibold mb-2">No CI Projects Yet</h3>
                        <p className="text-muted-foreground max-w-md mx-auto mb-6">
                            Configure a Webhook in your Gitea repository to start auto-discovering projects and generating reviews.
                        </p>
                        <div className="bg-muted p-4 rounded-md text-xs font-mono text-left w-full max-w-lg">
                            <div className="text-muted-foreground mb-2">Webhook URL:</div>
                            <div className="text-primary select-all">http://YOUR_SERVER_IP:8000/api/v1/webhooks/gitea</div>
                        </div>
                    </CardContent>
                </Card>
            ) : (
                <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
                    {projects.map(project => (
                        <Card key={project.id} className="hover:shadow-lg transition-all group border-l-4 border-l-transparent hover:border-l-primary">
                            <CardHeader>
                                <div className="flex justify-between items-start">
                                    <div className="space-y-1">
                                        <CardTitle className="text-xl break-all line-clamp-1 normal-case" title={project.name}>
                                            {project.name}
                                        </CardTitle>
                                        <CardDescription className="line-clamp-2 min-h-[2.5em]">
                                            {project.description || "No description provided"}
                                        </CardDescription>
                                    </div>
                                    <Badge variant="outline" className="font-mono text-xs">Public</Badge>
                                </div>
                            </CardHeader>
                            <CardContent>
                                <div className="space-y-4">
                                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                        <Clock className="w-4 h-4" />
                                        <span>
                                            AI 最后回复: {project.latest_pr_activity ? formatDistanceToNowStrict(new Date(project.latest_pr_activity), { addSuffix: true, locale: zhCN }) : '从无回复'}
                                        </span>
                                    </div>

                                    <div className="flex items-center gap-3 pt-2">
                                        <Link to={`/ci-integration/${project.id}`} className="flex-1">
                                            <Button className="w-full gap-2" variant="default">
                                                View Reviews <ArrowRight className="w-4 h-4" />
                                            </Button>
                                        </Link>
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            className="text-muted-foreground hover:text-destructive"
                                            onClick={() => handleDelete(project.id)}
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </Button>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
};

export default CIProjects;
